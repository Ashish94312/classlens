"""De-identification before anything leaves the server (HLD §8, LLD §5.5).

Pseudonymiser: teacher → T, students → S1..Sn (order of first appearance), other people named
in speech → N1..Nn. NameGuard: last check that no real name is left in outgoing text.
The real-name mapping lives only in memory for one run.
"""

import re

from classlens.models import TEACHER_CODE, UNKNOWN_SPEAKER, Cue, PseudonymisedTranscript, Transcript

# Words in Zoom display names that are devices, roles or placeholders, not names
LABEL_NOISE = {
    "iphone", "ipad", "android", "galaxy", "samsung", "redmi", "oppo", "vivo", "realme", "oneplus",
    "pixel", "laptop", "desktop", "macbook", "phone", "mobile", "tablet", "user", "guest", "zoom",
    "demo", "class", "host", "admin", "teacher", "trainer", "coach", "student", "test",
}
# Capitalised words that are not names. Speech-to-text capitalises the first word of every
# sentence; a word also seen in lowercase is skipped anyway, so this list mainly helps short clips.
NOT_NAMES = {
    "actually", "again", "alright", "also", "and", "anyone", "anyway", "audio", "basically",
    "because", "board", "but", "bye", "camera", "check", "checkmate", "chess", "class", "come",
    "correct", "dear", "everybody", "everyone", "exactly", "excellent", "fine", "first", "game",
    "good", "great", "guys", "hello", "here", "hey", "homework", "how", "kids", "king", "knight",
    "last", "let", "listen", "look", "madam", "mam", "move", "next", "nice", "now", "okay", "one",
    "perfect", "please", "puzzle", "queen", "remember", "right", "rook", "screen", "see", "sir",
    "sorry", "student", "students", "super", "sure", "teacher", "tell", "thank", "thanks", "that",
    "then", "there", "this", "today", "very", "video", "wait", "well", "what", "where", "which",
    "who", "why", "yeah", "yes", "you",
    # Capitalised mid-sentence by speech-to-text but not people: days, months, languages, places,
    # apps, chess openings
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "january",
    "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "english", "hindi", "malayalam", "tamil", "telugu", "kannada", "india",
    "indian", "america", "american", "google", "youtube", "whatsapp", "lichess", "chesscom",
    "sicilian", "italian", "french", "spanish", "london", "ruy", "lopez", "caro", "kann",
    "gambit", "defence", "defense", "opening", "god", "bishop", "pawn", "pawns", "piece", "pieces",
    "castle", "castling", "draw", "stalemate", "rank", "file", "goodbye", "goodnight",
    # Sentence starters: pronouns and helper verbs
    "she", "they", "them", "their", "his", "her", "him", "our", "your", "its", "can", "could",
    "would", "should", "will", "did", "does", "don", "are", "was", "were", "has", "have", "had",
    "not", "all", "some", "just", "only", "maybe", "after", "before", "when", "then", "also",
}
# A possible name: any capitalised word of 3+ letters, wherever it is ("Hello Ishaan",
# "Ishaan, your move", "ask Ishaan", "Ravi." alone on a line), but not a contraction ("Isn't").
# Ordinary words are filtered after.
CAPITALISED_WORD = re.compile(r"\b[A-Z][a-z]{2,}\b(?![’']t\b)")
# "tara.q@example.com"
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
# "+91 98765 43210", "9876543210"
PHONE = re.compile(r"\+?\d[\d\s-]{8,}\d")
# Possessive suffix in display names: "Priya’s iPhone" → "Priya iPhone"
POSSESSIVE = re.compile(r"[’']s\b", re.I)
# Letters only (any script): splits "__ISHAAN__MEHRA__" or "arjun.k@school" into words
LETTER_RUN = re.compile(r"[^\W\d_]+")
# A lowercase word, used to spot ordinary words: "bishop" in "the bishop moves"
LOWERCASE_WORD = re.compile(r"\b[a-z]+\b")
# The same code twice in a row, from a full name: "T T" → "T", "S3 S3" → "S3"
REPEATED_CODE = re.compile(r"\b([TSN]\d*)(?:\s+\1\b)+")
MIN_NAME_LENGTH = 3


class PrivacyError(Exception):
    """Raised instead of sending text that still contains a real name."""


def display_name_tokens(label: str) -> list[str]:
    """Name-like words in a display name: "Priya’s iPhone" → ["priya"]."""
    words = LETTER_RUN.findall(POSSESSIVE.sub("", label))
    tokens = []
    for word in words:
        token = word.casefold()
        if len(token) >= MIN_NAME_LENGTH and token not in LABEL_NOISE:
            tokens.append(token)
    return tokens


def names_pattern(tokens) -> re.Pattern | None:
    """One case-insensitive whole-word pattern for all tokens, longest first."""
    if not tokens:
        return None
    alternatives = "|".join(sorted(map(re.escape, tokens), key=len, reverse=True))
    return re.compile(rf"\b(?:{alternatives})\b", re.I)


class Pseudonymiser:
    """Replaces speakers with role codes and real names in the text with the same codes."""

    def __init__(self, teacher: str, known_names: frozenset[str] = frozenset()):
        self.teacher = teacher
        self.known_names = known_names  # casefolded names to replace even if no rule finds them

    def apply(self, transcript: Transcript) -> PseudonymisedTranscript:
        speaker_codes = self._assign_speaker_codes(transcript)
        name_codes = self._map_label_names(speaker_codes)
        name_codes.update(self._find_spoken_names(transcript, name_codes))
        name_codes.update(self._code_known_names(name_codes))
        pattern = names_pattern(name_codes)

        scrubbed = []
        for cue in transcript.cues:
            speaker = speaker_codes.get(cue.speaker, UNKNOWN_SPEAKER)
            text = self._scrub(cue.text, name_codes, pattern)
            scrubbed.append(Cue(cue.start, cue.end, speaker, text, cue.media))
        return PseudonymisedTranscript(Transcript(scrubbed), frozenset(name_codes))

    def _assign_speaker_codes(self, transcript: Transcript) -> dict[str, str]:
        """Display name → T, S1, S2… If no teacher was identified, nobody becomes T."""
        codes: dict[str, str] = {}
        if self.teacher != UNKNOWN_SPEAKER:
            codes[self.teacher] = TEACHER_CODE
        students = 0
        for cue in transcript.cues:
            if cue.speaker not in codes and cue.speaker != UNKNOWN_SPEAKER:
                students += 1
                codes[cue.speaker] = f"S{students}"
        return codes

    @staticmethod
    def _map_label_names(speaker_codes: dict[str, str]) -> dict[str, str]:
        """Name token → code. First names are mapped before other tokens, so a shared surname
        can't take over someone's first name."""
        name_codes: dict[str, str] = {}
        for label, code in speaker_codes.items():
            tokens = display_name_tokens(label)
            if tokens:
                name_codes.setdefault(tokens[0], code)
        for label, code in speaker_codes.items():
            for token in display_name_tokens(label)[1:]:
                name_codes.setdefault(token, code)
        return name_codes

    def _find_spoken_names(self, transcript: Transcript, known: dict[str, str]) -> dict[str, str]:
        """Names said in class that aren't in any display name (a child on a parent's device)
        → N1, N2… When unsure, a word is treated as a name: over-replacing costs readability,
        missing a name would send it to the AI model."""
        mid_sentence, sentence_start, lowercase = self._word_counts(transcript)

        found: dict[str, str] = {}
        for cue in transcript.cues:
            for match in CAPITALISED_WORD.finditer(cue.text):
                word = match.group(0).casefold()
                if word in known or word in found:
                    continue
                if self._is_ordinary_word(word, mid_sentence, sentence_start, lowercase):
                    continue
                found[word] = f"N{len(found) + 1}"
        return found

    def _code_known_names(self, coded: dict[str, str]) -> dict[str, str]:
        """Known names not found by the rules → the next N codes."""
        next_number = sum(1 for code in coded.values() if code.startswith("N")) + 1
        codes = {}
        for name in sorted(self.known_names - coded.keys()):
            codes[name] = f"N{next_number}"
            next_number += 1
        return codes

    @staticmethod
    def _word_counts(transcript: Transcript) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
        """Per casefolded word: times capitalised mid-sentence, capitalised at a sentence start, and
        written in lowercase."""
        mid_sentence, sentence_start, lowercase = {}, {}, {}
        for cue in transcript.cues:
            for word in LOWERCASE_WORD.findall(cue.text):
                lowercase[word] = lowercase.get(word, 0) + 1
            for match in CAPITALISED_WORD.finditer(cue.text):
                before = cue.text[: match.start()].rstrip()
                counts = mid_sentence if before and before[-1] not in ".?!" else sentence_start
                word = match.group(0).casefold()
                counts[word] = counts.get(word, 0) + 1
        return mid_sentence, sentence_start, lowercase

    @staticmethod
    def _is_ordinary_word(word: str, mid_sentence: dict, sentence_start: dict, lowercase: dict) -> bool:
        """A known non-name, or used like a common word: never capitalised mid-sentence and written in
        lowercase at least twice as often as capitalised. Speech-to-text sometimes writes a name in
        lowercase, so one lowercase use is not enough (measured on 6 real classes: names were left in
        25 lines with "any lowercase use", in 2 with this rule)."""
        if word in NOT_NAMES or word in LABEL_NOISE:
            return True
        return mid_sentence.get(word, 0) == 0 and lowercase.get(word, 0) >= 2 * sentence_start.get(word, 0)

    @staticmethod
    def _scrub(text: str, name_codes: dict[str, str], pattern: re.Pattern | None) -> str:
        text = EMAIL.sub("[email]", text)
        text = PHONE.sub("[phone]", text)
        if pattern is not None:
            text = pattern.sub(lambda match: name_codes[match.group(0).casefold()], text)
        return REPEATED_CODE.sub(r"\1", text)


class NameGuard:
    """Outbound check: refuse rather than send text that still contains a known real name."""

    def __init__(self, name_tokens: frozenset[str]):
        self._pattern = names_pattern(name_tokens)

    def check(self, text: str) -> None:
        if self._pattern is not None and self._pattern.search(text):
            raise PrivacyError("De-identification check failed, so nothing was sent to the AI model.")
