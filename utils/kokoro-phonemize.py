#!/usr/bin/env python3
"""
kokoro-phonemize  —  Misaki pronunciation lookup for kokoro-tts / kokoro-onnx

USAGE
    kp lead                              Single word: all pronunciations
    kp "word1" "word2" "word3"           Multiple words: each looked up
    kp "sentence"                        Heteronyms detected, others noted
    kp "sentence" --all                  All words: pronunciations + POS
    kp "sentence" -H                     Heteronyms only
    kp "sentence" --all -H               All heteronym variants, POS shown
    kp "I want a [dog]"                  Bracket = request pronunciation
    kp "Meat? [Dog] won a contest." -H   Brackets imply -H + bracketed words
    kp --list                            Educational heteronym reference
    kp --key                             Paste-ready Misaki guide for LLMs
    kp --key --cb                        Same, copied to clipboard
    kp "sentence" --cb                   Output + copy to clipboard
    kp "sentence" -C                     Disable colour output

DEPENDS
    pip install spacy && python -m spacy download en_core_web_sm
    pip install phonemizer               # espeak fallback for unknown words
    pip install pyperclip                # optional, for --cb clipboard support
"""

import sys
import re
import argparse
import os
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

ANSI_RE = re.compile(r'\033\[[0-9;]*m')

def stripansi(text):
    return ANSI_RE.sub('', text)

# Colour strings — replaced with '' when --no-color/-C is active
C = {
    'bold':   '\033[1m',
    'dim':    '\033[2m',
    'cyan':   '\033[36m',
    'green':  '\033[32m',
    'yellow': '\033[33m',
    'red':    '\033[31m',
    'reset':  '\033[0m',
}

def disable_color():
    for k in C:
        C[k] = ''

def b(s):   return f"{C['bold']}{s}{C['reset']}"
def dim(s): return f"{C['dim']}{s}{C['reset']}"
def cy(s):  return f"{C['cyan']}{s}{C['reset']}"
def gr(s):  return f"{C['green']}{s}{C['reset']}"
def yw(s):  return f"{C['yellow']}{s}{C['reset']}"
def rd(s):  return f"{C['red']}{s}{C['reset']}"

# ---------------------------------------------------------------------------
# Output manager  — single print path, accumulates clipboard buffer
# ---------------------------------------------------------------------------

class Output:
    """
    All script output goes through this object.
    Screen output preserves ANSI colour codes.
    Clipboard buffer is ANSI-stripped plain text.
    """
    def __init__(self):
        self._buf = []
        self._clipboard = False
        self._warned_large = False

    def enable_clipboard(self):
        self._clipboard = True

    def p(self, text=''):
        """Print a line and buffer it."""
        print(text)
        self._buf.append(stripansi(text))

    def warn(self, text):
        """Print a warning to stderr only (not buffered for clipboard)."""
        print(yw(f'Warning: {text}'), file=sys.stderr)

    def err(self, text):
        """Print an error to stderr only."""
        print(rd(f'Error: {text}'), file=sys.stderr)

    def flush(self):
        """Copy buffered content to clipboard if enabled."""
        if not self._clipboard:
            return
        content = '\n'.join(self._buf)
        try:
            import pyperclip
            pyperclip.copy(content)
            print(dim(f'✓ Copied to clipboard ({len(content)} chars)'), file=sys.stderr)
        except ImportError:
            self.err('pyperclip not installed. Run: pip install pyperclip')

out = Output()

# ---------------------------------------------------------------------------
# spaCy availability — checked once at startup
# ---------------------------------------------------------------------------

_nlp = None
_spacy_available = False

def _load_spacy():
    global _nlp, _spacy_available
    if _nlp is not None:
        return True
    try:
        import spacy
        _nlp = spacy.load('en_core_web_sm')
        _spacy_available = True
        return True
    except (ImportError, OSError):
        return False

def _spacy_warning():
    out.warn(
        'spaCy not found. Parts-of-speech (POS) info unavailable.\n'
        '         All pronunciation variants will be shown (like --all behaviour).\n'
        '         To install: pip install spacy && python -m spacy download en_core_web_sm'
    )

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Pronunciation:
    misaki:  str    # Misaki phoneme string
    pos:     str    # part-of-speech label
    hint:    str    # plain-English hint ("rhymes with X")
    ipa:     str = ''
    example: str = ''

@dataclass
class Entry:
    word:          str
    pronunciations: list = field(default_factory=list)
    note:          str = ''
    definition:    str = ''

# ---------------------------------------------------------------------------
# Heteronym dictionary
# ---------------------------------------------------------------------------

HETERONYMS = {

    # -----------------------------------------------------------------------
    # Vowel-change heteronyms (completely different vowels)
    # -----------------------------------------------------------------------

    'read': Entry('read',
        definition="Present tense rhymes with 'reed'; past tense rhymes with 'red'.",
        pronunciations=[
            Pronunciation('ɹid',  'verb – present / infinitive',            'rhymes with "reed"',  '/ɹiːd/', 'I read every day.'),
            Pronunciation('ɹɛd',  'verb – past tense / past participle',    'rhymes with "red"',   '/ɹɛd/',  'She read the letter.'),
        ]),

    'lead': Entry('lead',
        definition="The guiding verb rhymes with 'need'; the metal element rhymes with 'bed'.",
        pronunciations=[
            Pronunciation('lid',  'verb – to guide (present)',               'rhymes with "need"',  '/liːd/', 'Follow the path that will lead you home.'),
            Pronunciation('lɛd',  'noun – metal / verb – past tense',        'rhymes with "bed"',   '/lɛd/',  'Old pipes were made of lead.'),
        ]),

    'tear': Entry('tear',
        definition="A tear from crying rhymes with 'ear'; to tear paper rhymes with 'air'.",
        pronunciations=[
            Pronunciation('tɪɹ',  'noun – drop of water from crying',        'rhymes with "ear"',   '/tɪɹ/', 'A tear ran down her cheek.'),
            Pronunciation('tɛɹ',  'verb – to rip / noun – a rip',            'rhymes with "air"',   '/tɛɹ/', "Don't tear the page."),
        ]),

    'wind': Entry('wind',
        definition="Moving air rhymes with 'sinned'; the coiling verb rhymes with 'mind'.",
        pronunciations=[
            Pronunciation('wɪnd', 'noun – moving air, a breeze',             'rhymes with "sinned"', '/wɪnd/', 'The wind knocked over the sign.'),
            Pronunciation('wInd', 'verb – to coil or follow a winding path', 'rhymes with "mind"',   '/waɪnd/', 'Wind the thread around the spool.'),
        ]),

    'wound': Entry('wound',
        definition="An injury rhymes with 'mooned'; past tense of wind rhymes with 'found'.",
        pronunciations=[
            Pronunciation('wund',  'noun/verb – an injury / to injure',      'rhymes with "mooned"', '/wuːnd/', 'The wound healed slowly.'),
            Pronunciation('wWnd',  "verb – past tense of 'wind'",            'rhymes with "found"',  '/waʊnd/', 'She wound the clock.'),
        ]),

    'live': Entry('live',
        definition="The everyday verb rhymes with 'give'; the adjective (alive/on-air) rhymes with 'five'.",
        pronunciations=[
            Pronunciation('lɪv',  'verb – to reside or exist',               'rhymes with "give"',  '/lɪv/', 'They live in the city.'),
            Pronunciation('lIv',  'adj/adv – alive, in person, broadcasting','rhymes with "five"',  '/laɪv/', "It's a live concert."),
        ]),

    'close': Entry('close',
        definition="Nearby ends in soft /s/; the verb to shut ends in /z/.",
        pronunciations=[
            Pronunciation('klOs',  'adjective / adverb – nearby, intimate',  'rhymes with "dose"',  '/kloʊs/', 'Stand close to me.'),
            Pronunciation('klOz',  'verb – to shut, to end',                 'rhymes with "those"', '/kloʊz/', 'Please close the door.'),
        ]),

    # -----------------------------------------------------------------------
    # Noun=/s/ verb=/z/ voicing pairs
    # -----------------------------------------------------------------------

    'use': Entry('use',
        definition="The noun (a purpose) ends in soft /s/; the verb (to employ) ends in /z/.",
        pronunciations=[
            Pronunciation('jus',  'noun – a purpose or function',            'rhymes with "goose"',  '/juːs/', 'What is the use of that?'),
            Pronunciation('juz',  'verb – to employ or make use of',         'rhymes with "ooze"',   '/juːz/', 'Use the right tool.'),
        ]),

    'house': Entry('house',
        definition="A building ends in soft /s/; to provide accommodation ends in /z/.",
        pronunciations=[
            Pronunciation('hWs',  'noun – a building to live in',            'rhymes with "mouse"',  '/haʊs/', 'They bought a new house.'),
            Pronunciation('hWz',  'verb – to provide accommodation for',     'rhymes with "cows"',   '/haʊz/', 'The shelter houses fifty people.'),
        ]),

    'abuse': Entry('abuse',
        definition="The noun (mistreatment) ends in soft /s/; the verb (to mistreat) ends in /z/.",
        pronunciations=[
            Pronunciation('əbjˈus',  'noun – mistreatment, cruel language',  'uh-BYOOSS',  '/əˈbjuːs/', 'The report documented years of abuse.'),
            Pronunciation('əbjˈuz',  'verb – to mistreat, to misuse',        'uh-BYOOZZ',  '/əˈbjuːz/', "Don't abuse the privilege."),
        ]),

    'excuse': Entry('excuse',
        definition="The noun (a reason given) ends in soft /s/; the verb (to pardon) ends in /z/.",
        pronunciations=[
            Pronunciation('ɪkskjˈus',  'noun – a reason offered to justify', 'ek-SKYOOSS',  '/ɪksˈkjuːs/', "That's a weak excuse."),
            Pronunciation('ɪkskjˈuz',  'verb – to pardon, to release from',  'ek-SKYOOZZ',  '/ɪksˈkjuːz/', 'Please excuse the interruption.'),
        ]),

    'diffuse': Entry('diffuse',
        definition="The adjective (spread out) ends in soft /s/; the verb (to spread) ends in /z/.",
        pronunciations=[
            Pronunciation('dɪfjˈus',  'adjective – spread widely, not concentrated', 'dih-FYOOSS', '/dɪˈfjuːs/', 'A diffuse glow filled the room.'),
            Pronunciation('dɪfjˈuz',  'verb – to spread or scatter widely',           'dih-FYOOZZ', '/dɪˈfjuːz/', 'Plants diffuse oxygen into the air.'),
        ]),

    # -----------------------------------------------------------------------
    # Stress-shift: first syllable = noun/adj, second syllable = verb
    # -----------------------------------------------------------------------

    'present': Entry('present',
        definition="Noun/adjective stresses first syllable; verb stresses second.",
        pronunciations=[
            Pronunciation('pɹˈɛzᵻnt', 'noun – gift / adj – current, here',  'PREZ-ent',            "/ˈpɹɛzənt/", 'Here is your present.'),
            Pronunciation('pɹɪzˈɛnt',  'verb – to introduce or formally give','preh-ZENT',          "/pɹɪˈzɛnt/", 'She will present the award.'),
        ]),

    'record': Entry('record',
        definition="Noun stresses first syllable; verb stresses second.",
        pronunciations=[
            Pronunciation('ɹˈɛkɹd',   'noun – document, disc, achievement', 'REK-ord',             "/ˈɹɛkɹd/",  'She broke the world record.'),
            Pronunciation('ɹɪkˈɔɹd',  'verb – to capture audio or video',   'reh-CORD',            "/ɹɪˈkɔɹd/", 'Hit record to start.'),
        ]),

    'refuse': Entry('refuse',
        definition="Noun (garbage) stresses first syllable, ends /s/; verb (decline) stresses second, ends /z/.",
        pronunciations=[
            Pronunciation('ɹˈɛfjus',  'noun – waste, garbage',               'REF-yoos',            "/ˈɹɛfjuːs/", 'The refuse collectors came early.'),
            Pronunciation('ɹɪfjˈuz',  'verb – to say no, to decline',        'reh-FYOOZ',           "/ɹɪˈfjuːz/", 'I refuse to lie.'),
        ]),

    'permit': Entry('permit',
        definition="Noun (official pass) stresses first syllable; verb (to allow) stresses second.",
        pronunciations=[
            Pronunciation('pˈɜɹmᵻt',  'noun – an official pass or licence',  'PER-mit',             "/ˈpɜːmɪt/", 'Do you have a parking permit?'),
            Pronunciation('pɜɹmˈɪt',  'verb – to allow',                     'per-MIT',             "/pɜːˈmɪt/", "They won't permit entry."),
        ]),

    'conduct': Entry('conduct',
        definition="Noun (behaviour) stresses first syllable; verb stresses second.",
        pronunciations=[
            Pronunciation('kˈɑndʌkt',  'noun – behaviour, manner',           'CON-duct',            "/ˈkɒndʌkt/", 'His conduct was exemplary.'),
            Pronunciation('kəndˈʌkt',  'verb – to lead, carry out, direct',  'con-DUCT',            "/kənˈdʌkt/", 'She will conduct the orchestra.'),
        ]),

    'project': Entry('project',
        definition="Noun (a plan) stresses first syllable; verb (to display/throw) stresses second.",
        pronunciations=[
            Pronunciation('pɹˈɑʤɛkt',  'noun – a plan or undertaking',       'PRO-ject',            "/ˈpɹɒdʒɛkt/", 'Our project is due Friday.'),
            Pronunciation('pɹəʤˈɛkt',  'verb – to display, to cast forward', 'pro-JECT',            "/pɹəˈdʒɛkt/", 'Project the slides onto the wall.'),
        ]),

    'object': Entry('object',
        definition="Noun (a thing) stresses first syllable; verb (to protest) stresses second.",
        pronunciations=[
            Pronunciation('ˈɑbʤɛkt',  'noun – a physical thing',             'OB-ject',             "/ˈɒbdʒɛkt/", 'What is that object?'),
            Pronunciation('əbʤˈɛkt',  'verb – to protest or disagree',       'ob-JECT',             "/əbˈdʒɛkt/", 'I object to that claim.'),
        ]),

    'desert': Entry('desert',
        definition="The landscape stresses first syllable; the abandonment verb stresses second.",
        pronunciations=[
            Pronunciation('dˈɛzɜɹt',   'noun – arid sandy landscape',        'DEZ-ert',             "/ˈdɛzɜːt/", 'The Sahara is a vast desert.'),
            Pronunciation('dɪzˈɜɹt',   'verb – to abandon or leave behind',  'deh-ZERT',            "/dɪˈzɜːt/", 'He would never desert his friends.'),
        ]),

    'content': Entry('content',
        definition="Noun (subject matter) stresses first syllable; adjective/verb (satisfied) stresses second.",
        pronunciations=[
            Pronunciation('kˈɑntɛnt',  'noun – what something contains',     'CON-tent',            "/ˈkɒntɛnt/", 'The content of the speech was moving.'),
            Pronunciation('kəntˈɛnt',  'adj/verb – satisfied / to satisfy',  'con-TENT',            "/kənˈtɛnt/", 'She was content with the result.'),
        ]),

    'contest': Entry('contest',
        definition="Noun (competition) stresses first syllable; verb (to dispute) stresses second.",
        pronunciations=[
            Pronunciation('kˈɑntɛst',  'noun – a competition',               'CON-test',            "/ˈkɒntɛst/", 'She entered the contest.'),
            Pronunciation('kəntˈɛst',  'verb – to dispute or challenge',     'con-TEST',            "/kənˈtɛst/", 'They will contest the decision.'),
        ]),

    'increase': Entry('increase',
        definition="Noun (a rise) stresses first syllable; verb (to grow) stresses second.",
        pronunciations=[
            Pronunciation('ˈɪnkɹis',   'noun – a rise or growth',            'IN-crease',           "/ˈɪŋkɹiːs/", 'A significant increase in sales.'),
            Pronunciation('ɪnkɹˈis',   'verb – to grow, to make larger',     'in-CREASE',           "/ɪŋˈkɹiːs/", 'Prices will increase next year.'),
        ]),

    'upset': Entry('upset',
        definition="Noun/adjective stresses first syllable; verb stresses second.",
        pronunciations=[
            Pronunciation('ˈʌpsɛt',  'noun – surprise defeat / adj – distressed', 'UP-set', "/ˈʌpsɛt/", 'That was a major upset.'),
            Pronunciation('ʌpsˈɛt',  'verb – to disturb or overturn',             'up-SET', "/ʌpˈsɛt/", "Don't upset the balance."),
        ]),

    'produce': Entry('produce',
        definition="Noun (fresh food) stresses first syllable; verb (to make) stresses second.",
        pronunciations=[
            Pronunciation('pɹˈOdus',  'noun – fresh fruit and vegetables',   'PRO-duce',  "/ˈpɹoʊduːs/", 'Buy your produce at the farmers market.'),
            Pronunciation('pɹᵻdˈus',  'verb – to make, create, or manufacture', 'pro-DUCE', "/pɹəˈduːs/", 'The factory produces a thousand units daily.'),
        ]),

    'protest': Entry('protest',
        definition="Noun (a demonstration) stresses first syllable; verb (to object) stresses second.",
        pronunciations=[
            Pronunciation('pɹˈOtɛst',  'noun – a public demonstration or objection', 'PRO-test', "/ˈpɹoʊtɛst/", 'Thousands attended the protest.'),
            Pronunciation('pɹətˈɛst',  'verb – to object or demonstrate against',    'pro-TEST', "/pɹəˈtɛst/", 'They gathered to protest the decision.'),
        ]),

    'progress': Entry('progress',
        definition="Noun (advancement) stresses first syllable; verb (to advance) stresses second.",
        pronunciations=[
            Pronunciation('pɹˈɑɡɹᵻs',  'noun – forward movement or development', 'PROG-ress', "/ˈpɹɑːɡɹɛs/", 'We made real progress today.'),
            Pronunciation('pɹəɡɹˈɛs',  'verb – to move forward or develop',      'pro-GRESS', "/pɹəˈɡɹɛs/", 'The work will progress quickly.'),
        ]),

    'rebel': Entry('rebel',
        definition="Noun (a person who resists) stresses first syllable; verb (to resist) stresses second.",
        pronunciations=[
            Pronunciation('ɹˈɛbᵻl',  'noun – a person who resists authority', 'REB-el', "/ˈɹɛbəl/", 'She was known as a rebel.'),
            Pronunciation('ɹɪbˈɛl',  'verb – to resist or rise up against',   'reh-BEL', "/ɹɪˈbɛl/", 'Young people often rebel against rules.'),
        ]),

    'subject': Entry('subject',
        definition="Noun/adjective stresses first syllable; verb (to expose or submit) stresses second.",
        pronunciations=[
            Pronunciation('sˈʌbʤᵻkt',  'noun – a topic / grammar subject / citizen',  'SUB-ject', "/ˈsʌbdʒɪkt/", "What's the subject of the essay?"),
            Pronunciation('səbʤˈɛkt',  'verb – to expose or cause to undergo',         'sub-JECT', "/səbˈdʒɛkt/", "Don't subject them to unnecessary risk."),
        ]),

    'suspect': Entry('suspect',
        definition="Noun/adjective stresses first syllable; verb (to believe guilty) stresses second.",
        pronunciations=[
            Pronunciation('sˈʌspᵻkt',  'noun – a person under suspicion / adj – doubtful', 'SUS-pect', "/ˈsʌspɪkt/", 'The suspect was released.'),
            Pronunciation('səspˈɛkt',  'verb – to believe to be guilty or likely',          'sus-PECT', "/səˈspɛkt/", 'I suspect it will rain.'),
        ]),

    'conflict': Entry('conflict',
        definition="Noun (a struggle) stresses first syllable; verb (to clash) stresses second.",
        pronunciations=[
            Pronunciation('kˈɑnflɪkt',  'noun – a disagreement or battle',         'CON-flict', "/ˈkɒnflɪkt/", 'The conflict lasted three years.'),
            Pronunciation('kənflˈɪkt',  'verb – to be incompatible or to clash',   'con-FLICT', "/kənˈflɪkt/", 'These schedules conflict with each other.'),
        ]),

    'contract': Entry('contract',
        definition="Noun (a legal agreement) stresses first syllable; verb (to shrink or agree) stresses second.",
        pronunciations=[
            Pronunciation('kˈɑntɹækt',  'noun – a legally binding agreement',              'CON-tract', "/ˈkɒntɹækt/", 'Sign the contract before Friday.'),
            Pronunciation('kəntɹˈækt',  'verb – to shrink / to catch an illness / to hire', 'con-TRACT', "/kənˈtɹækt/", 'Cold metal contracts as it cools.'),
        ]),

    'contrast': Entry('contrast',
        definition="Noun (a difference) stresses first syllable; verb (to compare differences) stresses second.",
        pronunciations=[
            Pronunciation('kˈɑntɹæst',  'noun – a striking difference',             'CON-trast', "/ˈkɒntɹɑːst/", 'The contrast between them was stark.'),
            Pronunciation('kəntɹˈæst',  'verb – to compare or highlight differences','con-TRAST', "/kənˈtɹɑːst/", 'Contrast the two approaches.'),
        ]),

    'convert': Entry('convert',
        definition="Noun (a person who has changed beliefs) stresses first syllable; verb stresses second.",
        pronunciations=[
            Pronunciation('kˈɑnvɜɹt',  'noun – a person who has changed beliefs or religion', 'CON-vert', "/ˈkɒnvɜːt/", 'He became a convert to the cause.'),
            Pronunciation('kənvˈɜɹt',  'verb – to change form, belief, or function',          'con-VERT', "/kənˈvɜːt/", 'Convert the file to PDF.'),
        ]),

    'convict': Entry('convict',
        definition="Noun (a prisoner) stresses first syllable; verb (to find guilty) stresses second.",
        pronunciations=[
            Pronunciation('kˈɑnvɪkt',  'noun – a person serving a prison sentence',  'CON-vict', "/ˈkɒnvɪkt/", 'An escaped convict was on the loose.'),
            Pronunciation('kənvˈɪkt',  'verb – to find guilty in a court of law',    'con-VICT', "/kənˈvɪkt/", 'The jury voted to convict.'),
        ]),

    'export': Entry('export',
        definition="Noun (a product sent abroad) stresses first syllable; verb stresses second.",
        pronunciations=[
            Pronunciation('ˈɛkspOɹt',  'noun – a good sold and sent to another country', 'EX-port', "/ˈɛkspɔːt/", 'Oil is the country\'s main export.'),
            Pronunciation('ɛkspˈOɹt',  'verb – to send goods abroad for sale',           'ex-PORT', "/ɪkˈspɔːt/", 'They export timber to Europe.'),
        ]),

    'import': Entry('import',
        definition="Noun (a good brought from abroad) stresses first syllable; verb stresses second.",
        pronunciations=[
            Pronunciation('ˈɪmpOɹt',  'noun – a good brought in from another country', 'IM-port', "/ˈɪmpɔːt/", 'Cheap imports flooded the market.'),
            Pronunciation('ɪmpˈOɹt',  'verb – to bring in from another country',       'im-PORT', "/ɪmˈpɔːt/", 'They import coffee from Colombia.'),
        ]),

    'insert': Entry('insert',
        definition="Noun (something placed inside) stresses first syllable; verb stresses second.",
        pronunciations=[
            Pronunciation('ˈɪnsɜɹt',  'noun – a thing placed inside something else',  'IN-sert', "/ˈɪnsɜːt/", 'Remove the insert from the envelope.'),
            Pronunciation('ɪnsˈɜɹt',  'verb – to place something inside',             'in-SERT', "/ɪnˈsɜːt/", 'Insert the key into the lock.'),
        ]),

    'insult': Entry('insult',
        definition="Noun (an offensive remark) stresses first syllable; verb (to offend) stresses second.",
        pronunciations=[
            Pronunciation('ˈɪnsʌlt',  'noun – an offensive remark or action', 'IN-sult', "/ˈɪnsʌlt/", "That comment was a deliberate insult."),
            Pronunciation('ɪnsˈʌlt',  'verb – to offend or disrespect',       'in-SULT', "/ɪnˈsʌlt/", "Don't insult the host."),
        ]),

    'transfer': Entry('transfer',
        definition="Noun (a movement from one place to another) stresses first syllable; verb stresses second.",
        pronunciations=[
            Pronunciation('tɹˈænsfɜɹ',  'noun – a movement or change of location/ownership', 'TRANS-fer', "/ˈtɹænsfɜː/", 'The transfer was completed at midnight.'),
            Pronunciation('tɹænsfˈɜɹ',  'verb – to move or hand over to another',            'trans-FER', "/tɹænsˈfɜː/", 'Transfer the funds to the new account.'),
        ]),

    'survey': Entry('survey',
        definition="Noun (a study or measurement) stresses first syllable; verb (to examine) stresses second.",
        pronunciations=[
            Pronunciation('sˈɜɹvA',  'noun – a study, poll, or land measurement', 'SUR-vey', "/ˈsɜːveɪ/", 'The survey revealed widespread concern.'),
            Pronunciation('sɜɹvˈA',  'verb – to examine or measure systematically', 'sur-VEY', "/sɜːˈveɪ/", 'Engineers will survey the site tomorrow.'),
        ]),

    'escort': Entry('escort',
        definition="Noun (a companion or guard) stresses first syllable; verb (to accompany) stresses second.",
        pronunciations=[
            Pronunciation('ˈɛskOɹt',  'noun – a person or group accompanying another', 'ES-cort', "/ˈɛskɔːt/", 'A police escort led the motorcade.'),
            Pronunciation('ɪskˈOɹt',  'verb – to accompany for protection or courtesy', 'es-CORT', "/ɪˈskɔːt/", 'He offered to escort her to the door.'),
        ]),

    # -----------------------------------------------------------------------
    # Stress-shift: ambiguous — cannot resolve from POS alone
    # -----------------------------------------------------------------------

    'row': Entry('row',
        note="The argument sense (rhymes with 'now') is chiefly British English.",
        definition="A line or paddling rhymes with 'go'; a noisy argument (British) rhymes with 'now'.",
        pronunciations=[
            Pronunciation('ɹO',   'noun – a line / verb – to paddle a boat', 'rhymes with "go"',    '/ɹoʊ/', 'Row your boat gently.'),
            Pronunciation('ɹW',   'noun – a noisy argument (British)',        'rhymes with "now"',   '/ɹaʊ/', 'They had a terrible row.'),
        ]),

    'bow': Entry('bow',
        definition="Weapon/ribbon bow rhymes with 'go'; bending forward or ship's front rhymes with 'now'.",
        pronunciations=[
            Pronunciation('bO',   'noun – weapon / violin bow / ribbon',      'rhymes with "go"',    '/boʊ/', 'She tied a bow on the gift.'),
            Pronunciation('bW',   'verb – to bend / noun – front of a ship',  'rhymes with "now"',   '/baʊ/', 'The actors took a bow.'),
        ]),

    'sow': Entry('sow',
        definition="To plant seeds rhymes with 'go'; a female pig rhymes with 'now'.",
        pronunciations=[
            Pronunciation('sO',   'verb – to scatter seeds in the ground',    'rhymes with "go"',    '/soʊ/', 'Sow the seeds in spring.'),
            Pronunciation('sW',   'noun – a female pig',                      'rhymes with "now"',   '/saʊ/', 'The sow and her piglets.'),
        ]),

    'bass': Entry('bass',
        definition="Low musical frequency rhymes with 'face'; the fish rhymes with 'mass'.",
        pronunciations=[
            Pronunciation('bAs',  'noun/adj – low musical frequency',         'rhymes with "face"',  '/beɪs/', 'Turn up the bass.'),
            Pronunciation('bæs',  'noun – a freshwater or saltwater fish',    'rhymes with "mass"',  '/bæs/',  'He caught a large bass.'),
        ]),

    'dove': Entry('dove',
        note="'Dove' as past tense of 'dive' is American English; Brits say 'dived'.",
        definition="The bird rhymes with 'love'; American past tense of 'dive' rhymes with 'stove'.",
        pronunciations=[
            Pronunciation('dʌv',  'noun – the bird, a symbol of peace',      'rhymes with "love"',  '/dʌv/', 'A white dove landed nearby.'),
            Pronunciation('dOv',  "verb – past tense of 'dive' (AmEng)",     'rhymes with "stove"', '/doʊv/', 'She dove into the pool.'),
        ]),

    'putting': Entry('putting',
        definition="Placing something rhymes with 'footing'; the golf stroke rhymes with 'cutting'.",
        pronunciations=[
            Pronunciation('pˈʊtɪŋ', 'verb – placing something',             'rhymes with "footing"', "/ˈpʊtɪŋ/", 'She was putting the books away.'),
            Pronunciation('pˈʌtɪŋ', 'verb – making a short golf stroke',    'rhymes with "cutting"', "/ˈpʌtɪŋ/", 'He spent an hour putting on the green.'),
        ]),

    # -----------------------------------------------------------------------
    # -ate suffix: noun/adj = reduced /ɪt/, verb = full /eɪt/
    # -----------------------------------------------------------------------

    'graduate': Entry('graduate',
        definition="As a noun or adjective, the final syllable is reduced to /ɪt/. As a verb, it is the full /eɪt/.",
        pronunciations=[
            Pronunciation('ɡɹˈæʤuᵻt', 'noun/adj – a person who has earned a degree', 'GRAD-yoo-it', "/ˈɡɹædʒuɪt/", 'She is a graduate of MIT.'),
            Pronunciation('ɡɹˈæʤuAt', 'verb – to complete a degree programme',        'GRAD-yoo-ayt', "/ˈɡɹædʒueɪt/", 'He will graduate in June.'),
        ]),

    'separate': Entry('separate',
        definition="As a noun or adjective, the final syllable is reduced. As a verb, it rhymes with 'rate'.",
        pronunciations=[
            Pronunciation('sˈɛpɹᵻt', 'noun/adj – not joined; an individual item',    'SEP-rit',   "/ˈsɛpɹɪt/",   'Keep them in separate boxes.'),
            Pronunciation('sˈɛpɹAt', 'verb – to divide or move apart',               'SEP-rayt',  "/ˈsɛpɹeɪt/",  'Separate the egg whites from the yolks.'),
        ]),

    'moderate': Entry('moderate',
        definition="As a noun or adjective, the final syllable is reduced. As a verb, it rhymes with 'rate'.",
        pronunciations=[
            Pronunciation('mˈɑdɹᵻt', 'noun/adj – not extreme; a middle-ground person', 'MOD-rit',   "/ˈmɒdɹɪt/",  'He holds moderate political views.'),
            Pronunciation('mˈɑdɹAt', 'verb – to preside over; to lessen in intensity', 'MOD-rayt',  "/ˈmɒdɹeɪt/", 'She will moderate the debate.'),
        ]),

    'estimate': Entry('estimate',
        definition="As a noun, the final syllable is reduced to /ɪt/. As a verb, it ends in /eɪt/.",
        pronunciations=[
            Pronunciation('ˈɛstᵻmᵻt', 'noun – an approximate calculation or judgement', 'ES-ti-mit',  "/ˈɛstɪmɪt/",  "The estimate came in under budget."),
            Pronunciation('ˈɛstᵻmAt', 'verb – to calculate or judge approximately',     'ES-ti-mayt', "/ˈɛstɪmeɪt/", 'Experts estimate it will take a year.'),
        ]),

    'advocate': Entry('advocate',
        definition="As a noun (a supporter or lawyer), the final syllable is /ɪt/. As a verb, it ends in /eɪt/.",
        pronunciations=[
            Pronunciation('ˈædvᵻkᵻt', 'noun – a supporter; a lawyer who pleads in court', 'AD-vo-kit',  "/ˈædvəkɪt/",  'She is a passionate advocate for reform.'),
            Pronunciation('ˈædvᵻkAt', 'verb – to publicly support or recommend',          'AD-vo-kayt', "/ˈædvəkeɪt/", 'They advocate for better public transport.'),
        ]),

    'delegate': Entry('delegate',
        definition="As a noun (a representative), the final syllable is /ɪt/. As a verb (to assign), it ends in /eɪt/.",
        pronunciations=[
            Pronunciation('dˈɛlᵻɡᵻt', 'noun – a representative chosen to act for others', 'DEL-eh-git',  "/ˈdɛlɪɡɪt/",  'Each country sent a delegate.'),
            Pronunciation('dˈɛlᵻɡAt', 'verb – to assign a task or responsibility to another', 'DEL-eh-gayt', "/ˈdɛlɪɡeɪt/", 'Learn to delegate effectively.'),
        ]),

    'elaborate': Entry('elaborate',
        definition="As an adjective (detailed or complex), the final syllable is /ɪt/. As a verb (to expand on), it ends in /eɪt/.",
        pronunciations=[
            Pronunciation('ɪlˈæbɹᵻt', 'adj – highly detailed, intricate, or complex',    'eh-LAB-rit',  "/ɪˈlæbɹɪt/",  'The set design was elaborate.'),
            Pronunciation('ɪlˈæbɹAt', 'verb – to give more detail or expand on something', 'eh-LAB-rayt', "/ɪˈlæbɹeɪt/", 'Could you elaborate on that point?'),
        ]),

    # -----------------------------------------------------------------------
    # -ed: verb past tense = one syllable; adjective = two syllables
    # -----------------------------------------------------------------------

    'aged': Entry('aged',
        definition="As a verb (past tense of 'age'), it is one syllable. As an adjective meaning elderly, it is two syllables.",
        pronunciations=[
            Pronunciation('Ajd',    "verb – past tense of 'age': matured",      'one syllable: ayjd', '/eɪdʒd/', 'The whisky aged in oak barrels.'),
            Pronunciation('ˈAjᵻd', 'adj – old or elderly; of a specified age', 'two syllables: AY-jid', "/ˈeɪdʒɪd/", 'She cared for her aged parents.'),
        ]),

    'blessed': Entry('blessed',
        definition="As a verb (past tense of 'bless'), one syllable. As an adjective (holy, fortunate), two syllables.",
        pronunciations=[
            Pronunciation('blɛst',    "verb – past tense of 'bless'",                  'one syllable: blest',    '/blɛst/',     'The priest blessed the congregation.'),
            Pronunciation('blˈɛsᵻd', 'adj – holy, consecrated, or deeply fortunate',  'two syllables: BLES-sid', "/ˈblɛsɪd/", 'They lived a blessed life.'),
        ]),

    'learned': Entry('learned',
        definition="As a verb (past tense of 'learn'), one syllable. As an adjective meaning scholarly, two syllables.",
        pronunciations=[
            Pronunciation('lɜɹnd',    "verb – past tense of 'learn'",               'one syllable: lernd',    '/lɜːnd/',    'She learned quickly.'),
            Pronunciation('lˈɜɹnᵻd', 'adj – having great knowledge, scholarly',    'two syllables: LER-nid', "/ˈlɜːnɪd/", 'He was a learned professor.'),
        ]),

    'dogged': Entry('dogged',
        definition="As a verb (past tense of 'dog'), one syllable. As an adjective meaning tenacious, two syllables.",
        pronunciations=[
            Pronunciation('dˈɑɡd',   "verb – past tense of 'dog': to follow persistently", 'one syllable: dogd',    '/dɒɡd/',    'Bad luck has dogged him for years.'),
            Pronunciation('dˈɑɡᵻd', 'adj – stubbornly persistent, tenacious',              'two syllables: DOG-id', "/ˈdɒɡɪd/", 'Her dogged determination paid off.'),
        ]),

    'beloved': Entry('beloved',
        definition="As a verb (past tense), two syllables. As an adjective or noun in formal/literary use, three syllables.",
        pronunciations=[
            Pronunciation('bɪlˈʌvd',   "verb – past tense: was loved",                   'two syllables: bih-LUVD',    '/bɪˈlʌvd/',  'She was beloved by all who knew her.'),
            Pronunciation('bɪlˈʌvᵻd', 'adj/noun – deeply loved (formal, literary, religious)', 'three syllables: bih-LUV-id', "/bɪˈlʌvɪd/", 'Dearly beloved, we are gathered here.'),
        ]),

    # -----------------------------------------------------------------------
    # Miscellaneous
    # -----------------------------------------------------------------------

    'minute': Entry('minute',
        definition="The time unit is MIN-it; the adjective meaning tiny is my-NYOOT.",
        pronunciations=[
            Pronunciation('mˈɪnᵻt',   'noun – 60 seconds, a moment',         'MIN-it',              "/ˈmɪnɪt/",   'Wait just a minute.'),
            Pronunciation('mInjˈut',   'adjective – extremely small, tiny',    'my-NYOOT',            "/maɪˈnjuːt/", 'A minute speck of dust.'),
        ]),

    'invalid': Entry('invalid',
        definition="The adjective (not valid/null) stresses second syllable; the noun (a sick person, archaic) stresses first.",
        pronunciations=[
            Pronunciation('ɪnvˈælɪd', 'adj – not valid, null, without legal force', 'in-VAL-id', "/ɪnˈvælɪd/", 'Your ticket is invalid after midnight.'),
            Pronunciation('ˈɪnvᵻlᵻd', 'noun – a person weakened by illness (dated)', 'IN-va-lid', "/ˈɪnvəlɪd/", 'He returned from the war as an invalid.'),
        ]),

    'number': Entry('number',
        note="'More numb' is recognised in dictionaries but rarely used in practice.",
        definition="A numeral rhymes with 'plumber'; the comparative of 'numb' rhymes with 'hummer' with a different vowel.",
        pronunciations=[
            Pronunciation('nˈʌmbɜɹ', 'noun/verb – a numeral; to assign numbers to', 'NUM-ber (rhymes with "plumber")', '/ˈnʌmbɜː/', 'What number are you thinking of?'),
            Pronunciation('nˈʌmɜɹ',  'adj – more numb, having less feeling',        'NUM-er (no b sound)',             '/ˈnʌmɜː/',  "My fingers grew number in the cold."),
        ]),

}

# ---------------------------------------------------------------------------
# POS → pronunciation index
# ---------------------------------------------------------------------------

def _select_index(word, pos, tag):
    """Return the index of the best pronunciation for the given POS, or -1 if ambiguous."""
    w = word.lower()

    # ---- Special cases: verb tense / POS determines vowel, not just stress ----
    if w == 'read':
        return 1 if tag in ('VBD', 'VBN') else 0
    if w == 'lead':
        return 1 if (pos == 'NOUN' or tag == 'VBD') else 0
    if w in ('tear', 'wind', 'wound'):
        return 0 if pos == 'NOUN' else 1
    if w == 'live':
        return 1 if pos == 'ADJ' else 0
    if w == 'close':
        return 0 if pos in ('ADJ', 'ADV') else 1
    if w == 'minute':
        return 1 if pos == 'ADJ' else 0
    if w == 'invalid':
        return 0 if pos == 'ADJ' else (1 if pos == 'NOUN' else -1)
    if w == 'number':
        return 1 if pos == 'ADJ' else 0
    if w == 'beloved':
        return 0 if tag in ('VBD', 'VBN') else (1 if pos == 'ADJ' else -1)

    # ---- noun=/s/ verb=/z/ voicing pairs ----
    if w in ('use', 'house', 'abuse', 'excuse', 'diffuse'):
        return 0 if pos == 'NOUN' else (1 if pos == 'VERB' else -1)

    # ---- -ate suffix: noun/adj = reduced /ɪt/, verb = full /eɪt/ ----
    if w in ('graduate', 'separate', 'moderate', 'estimate', 'advocate',
             'delegate', 'elaborate'):
        return 0 if pos in ('NOUN', 'ADJ') else (1 if pos == 'VERB' else -1)

    # ---- -ed: verb past tense = 1 syllable, adjective = 2 syllables ----
    if w in ('aged', 'blessed', 'learned', 'dogged'):
        return 0 if tag in ('VBD', 'VBN') else (1 if pos == 'ADJ' else -1)

    # ---- Standard noun-stress / verb-stress shift ----
    if w in (
        'present', 'record', 'refuse', 'object', 'permit',
        'conduct', 'project', 'desert', 'content', 'contest',
        'increase', 'upset',
        'produce', 'protest', 'progress', 'rebel',
        'subject', 'suspect',
        'conflict', 'contract', 'contrast', 'convert', 'convict',
        'export', 'import', 'insert', 'insult', 'transfer',
        'survey', 'escort',
    ):
        return 0 if pos == 'NOUN' else (1 if pos == 'VERB' else -1)

    # ---- Semantically ambiguous: cannot resolve from POS alone ----
    if w in ('row', 'bow', 'sow', 'bass', 'dove', 'putting', 'number'):
        return -1

    return -1

# ---------------------------------------------------------------------------
# Bracket handling
# ---------------------------------------------------------------------------

BRACKET_RE = re.compile(r'\[([^\]]+)\]')

def _extract_bracketed(text):
    return BRACKET_RE.findall(text)

def _strip_brackets(text):
    return BRACKET_RE.sub(r'\1', text)

# ---------------------------------------------------------------------------
# Heteronym / hyphen lookup
# ---------------------------------------------------------------------------

def _lookup_token(token_text):
    """Look up word or hyphenated compound. Returns Entry or None."""
    w = token_text.lower()
    if w in HETERONYMS:
        return HETERONYMS[w]
    if '-' in w:
        for part in w.split('-'):
            if part in HETERONYMS:
                return HETERONYMS[part]
    return None

# ---------------------------------------------------------------------------
# espeak fallback
# ---------------------------------------------------------------------------

def _espeak_fallback(word):
    """Return Misaki phonemes via espeak/phonemizer, or None."""
    try:
        import re as _re
        from phonemizer.backend import EspeakBackend
        FROM_ESPEAKS = sorted({
            '\u0303':'','a^ɪ':'I','a^ʊ':'W','d^ʒ':'ʤ','e':'A','e^ɪ':'A',
            'r':'ɹ','t^ʃ':'ʧ','x':'k','ç':'k','ɐ':'ə','ɔ^ɪ':'Y',
            'ə^l':'ᵊl','ɚ':'əɹ','ɬ':'l','ʔ':'t','ʔn':'tᵊn',
            'ʔˌn\u0329':'tᵊn','ʲ':'','ʲO':'jO','ʲQ':'jQ',
        }.items(), key=lambda kv: -len(kv[0]))
        def from_espeak(ps):
            for old, new in FROM_ESPEAKS:
                ps = ps.replace(old, new)
            ps = _re.sub(r'(\S)\u0329', r'ᵊ\1', ps).replace(chr(809), '')
            return ps.replace('o^ʊ','O').replace('ɜːɹ','ɜɹ').replace('ɜː','ɜɹ') \
                     .replace('ɪə','iə').replace('ː','').replace('^','')
        backend = EspeakBackend('en-us', preserve_punctuation=False, with_stress=True, tie='^')
        result = backend.phonemize([word])
        raw = result[0].strip() if result else ''
        return from_espeak(raw) if raw else None
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_pron(word, p, chosen=False, show_pos_tag=None):
    """
    Format one Pronunciation line.
    chosen=True     → highlight with ▶
    show_pos_tag    → if set, display the spaCy POS tag that selected this
    """
    marker = f'{yw("▶")} ' if chosen else '  '
    ipa    = f'  {dim(p.ipa)}' if p.ipa else ''
    ex     = f'\n    {dim("e.g.")} {dim(chr(8220)+p.example+chr(8221))}' if p.example else ''
    pos_chosen = f'  {dim("← spaCy: "+show_pos_tag)}' if show_pos_tag else ''
    return (
        f'{marker}{cy(f"[{word}](/{p.misaki}/)")}  '
        f'{gr(p.pos)}  — {p.hint}{ipa}{pos_chosen}{ex}'
    )

# ---------------------------------------------------------------------------
# Single-word display
# ---------------------------------------------------------------------------

def show_word(word, show_all=False):
    entry = _lookup_token(word)
    if entry is None:
        fallback = _espeak_fallback(word)
        if fallback:
            out.p(f'\n{b(word)}  {dim("(not a heteronym — single pronunciation)")}')
            out.p(f'  {cy(f"[{word}](/{fallback}/)")}  {dim("(via espeak)")}')
        else:
            out.p(f'\n{b(word)}  {dim("(not found — install phonemizer for fallback)")}')
        return

    out.p(f'\n{b(entry.word)}  {dim("— heteronym")}')
    if entry.definition:
        out.p(f'  {entry.definition}')
    if entry.note:
        out.p(f'  {dim("note: "+entry.note)}')
    out.p()
    for i, p in enumerate(entry.pronunciations):
        out.p(_fmt_pron(word, p))
        out.p()

# ---------------------------------------------------------------------------
# Sentence display
# ---------------------------------------------------------------------------

def show_sentence(sentence, heteronyms_only=False, show_all=False, annotate=False):
    """
    Process a sentence:
      default          — heteronyms + [bracketed] words
      --all            — every token, with POS, pronunciations
      -H               — heteronyms only (no other words)
      --all -H         — all heteronym variants, POS shown
      [brackets]       — always included regardless of -H

    Bug fix: deduplication is now by (word, chosen_idx) so the same word
    appearing twice with different POS (e.g. "close the door, stand close")
    will be shown twice with its respective resolved pronunciation.
    """
    bracketed_words = set(w.lower() for w in _extract_bracketed(sentence))
    # Brackets present → implies heteronym mode for the rest (user said so)
    if bracketed_words and not show_all:
        heteronyms_only = True

    clean = _strip_brackets(sentence)

    have_spacy = _load_spacy()
    if not have_spacy:
        _spacy_warning()

    tokens = []  # (text, pos, tag)  — pos/tag empty if no spaCy
    if have_spacy:
        doc = _nlp(clean)
        tokens = [(t.text, t.pos_, t.tag_) for t in doc]
    else:
        # Plain word-split fallback; strip punctuation per token
        for raw in clean.split():
            word = raw.strip('.,!?;:\'"()[]')
            if word:
                tokens.append((word, '', ''))

    # Build findings list.
    # Deduplication is by (word_lower, chosen_idx) so that the same word
    # appearing in different grammatical roles (e.g. "close" as verb vs
    # adjective) is shown separately if it resolves to a different pronunciation.
    findings = []
    seen_keys = set()   # (word_lower, chosen_idx) pairs already added

    for word_text, pos, tag in tokens:
        w = word_text.lower()

        is_bracketed = (w in bracketed_words)
        entry = _lookup_token(w)
        is_heteronym = entry is not None

        # Compute idx before dedup check so we can dedup on (word, idx)
        idx = _select_index(w, pos, tag) if is_heteronym and have_spacy else -1

        dedup_key = (w, idx)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        if show_all:
            pass
        elif heteronyms_only:
            if not is_heteronym and not is_bracketed:
                continue
        else:
            # Default: heteronyms + bracketed
            if not is_heteronym and not is_bracketed:
                continue

        pos_label = f'{pos}/{tag}' if pos else ''
        source = ('both'      if is_bracketed and is_heteronym else
                  'bracketed' if is_bracketed else
                  'heteronym' if is_heteronym else
                  'all')
        findings.append((word_text, entry, idx, source, pos_label))

    # Bracketed words not found among tokens (e.g. multi-word phrases)
    for bw in bracketed_words:
        if bw not in {f[0].lower() for f in findings}:
            entry = _lookup_token(bw)
            findings.append((bw, entry, -1, 'bracketed', ''))

    if not findings:
        out.p(f'\nNo known heteronyms found in: "{sentence}"')
        if not show_all:
            out.p(dim('  (Use --all / -A to show all words, or [bracket] specific words)'))
        return

    word_count = len(tokens)
    het_count  = sum(1 for f in findings if f[3] in ('heteronym','both'))
    hint_parts = []
    if not show_all and het_count:
        hint_parts.append(f'{het_count} heteronym instance{"s" if het_count!=1 else ""} detected')
    if show_all:
        hint_parts.append(f'{word_count} words')
    if not have_spacy:
        hint_parts.append('no POS — all variants shown')
    if hint_parts:
        out.p(dim(f'\n  [{", ".join(hint_parts)} — use -H for heteronyms only, [bracket] for specific words, --all for a verbose output.]'))

    out.p(f'\nSentence: {sentence}\n')

    src_labels = {
        'heteronym': yw('heteronym'),
        'bracketed': gr('requested'),
        'both':      f'{yw("heteronym")} + {gr("requested")}',
        'all':       dim('word'),
    }

    for word_text, entry, idx, source, pos_label in findings:
        pos_info = f'  {dim("spaCy: "+pos_label)}' if pos_label else ''
        out.p(f'  {b(word_text)}  [{src_labels[source]}]{pos_info}')

        if entry is not None:
            if entry.definition:
                out.p(f'    {dim(entry.definition)}')
            if entry.note:
                out.p(f'    {dim("note: " + entry.note)}')

            # Always show all variants; mark the POS-resolved choice with ▶.
            # Previously the unchosen variant was hidden when idx >= 0, which
            # made it impossible to verify or copy-paste the alternative.
            for i, p in enumerate(entry.pronunciations):
                chosen = (i == idx)
                pos_note = pos_label if chosen and pos_label else None
                out.p('  ' + _fmt_pron(word_text, p, chosen=chosen, show_pos_tag=pos_note))

        else:
            # Not a heteronym — espeak fallback
            fallback = _espeak_fallback(word_text)
            if fallback:
                out.p(f'    → {cy(f"[{word_text}](/{fallback}/)")}  {dim("(via espeak)")}')
            else:
                out.p(f'    → {dim("(install phonemizer for pronunciation)")}')
        out.p()

    if annotate:
        out.p('Annotated sentence:\n')
        if have_spacy:
            # Walk the spaCy token list so each occurrence gets its own
            # POS-resolved pronunciation in a single pass — no regex
            # substitution means no risk of double-annotating the same word.
            parts = []
            for token in doc:
                w = token.text.lower()
                entry = _lookup_token(w)
                if entry is not None:
                    tidx = _select_index(w, token.pos_, token.tag_)
                    misaki = entry.pronunciations[max(tidx, 0)].misaki
                    parts.append(f'[{token.text}](/{misaki}/)' + token.whitespace_)
                else:
                    parts.append(token.text_with_ws)
            result = ''.join(parts).strip()
        else:
            # No spaCy: best-effort single-pass, one pronunciation per unique
            # word (can't disambiguate multiple occurrences without POS).
            result = clean
            seen_annotation: set = set()
            for word_text, entry, idx, source, _ in sorted(findings, key=lambda x: -len(x[0])):
                w = word_text.lower()
                if w in seen_annotation:
                    continue
                seen_annotation.add(w)
                if entry is not None:
                    misaki = entry.pronunciations[max(idx, 0)].misaki
                else:
                    misaki = _espeak_fallback(word_text) or '?'
                replacement = f'[{word_text}](/{misaki}/)'
                result = re.sub(re.escape(word_text), replacement, result, flags=re.IGNORECASE)
        out.p(f'  {result}\n')

# ---------------------------------------------------------------------------
# --list  (educational)
# ---------------------------------------------------------------------------

def show_list():
    out.p(f"""
{b("What is a heteronym?")}

A heteronym is a word spelled identically as another word but with a
different meaning and a different pronunciation.

This matters for text-to-speech (TTS) systems: the system must understand
the grammar of a sentence — not just its spelling — to say the word correctly.

Example:
  "Please {b("read")} this."       → {cy("ɹid")}  (present tense, rhymes with "reed")
  "I already {b("read")} it."      → {cy("ɹɛd")}  (past tense, rhymes with "red")

The {b('[word](/phonemes/)')} syntax in kokoro-onnx lets you override pronunciation
when the automatic system gets it wrong.

{b(f"Known heteronyms ({len(HETERONYMS)} words):")}
""")
    for word in sorted(HETERONYMS):
        entry = HETERONYMS[word]
        out.p(f'  {b(word)}')
        if entry.definition:
            out.p(f'    {entry.definition}')
        for p in entry.pronunciations:
            ipa = f'  {dim(p.ipa)}' if p.ipa else ''
            ex  = f'  {dim(chr(8220)+p.example+chr(8221))}' if p.example else ''
            out.p(f'    {cy(f"[{word}](/{p.misaki}/)")}  {gr(p.pos)}  — {p.hint}{ipa}{ex}')
        if entry.note:
            out.p(f'    {dim("note: "+entry.note)}')
        out.p()

# ---------------------------------------------------------------------------
# --key  (Misaki guide, pasteable to an LLM)
# ---------------------------------------------------------------------------

MISAKI_KEY = r"""
# Misaki Phoneme Reference  (kokoro-tts / kokoro-onnx)
# Paste this into an LLM context when asking for pronunciation help.
# Syntax to override TTS pronunciation:  [word](/phonemes/)
# Example:  [lead](/lɛd/) pipe

## Stress marks
ˈ   primary stress    ˌ   secondary stress

## Consonants (IPA)
b d f h j(=y) k l m n p s t v w z
ɡ  hard-g (get)      ŋ  ng (sung)       ɹ  r (red)
ʃ  sh (shin)         ʒ  zh (Asia)       ð  soft-th (than)
θ  hard-th (thin)

## Consonant clusters
ʤ  j/dg (jump, lunge)    ʧ  ch (chump, lunch)

## Vowels (IPA)
ə  schwa (a banana)    i  ee (easy)      u  oo (flu)
ɑ  ah (spa)            ɔ  aw (all)       ɛ  e (bed, hair)
ɜ  er (her)            ɪ  i (brick)      ʊ  oo (wood)
ʌ  u (sun)

## Diphthongs (uppercase = Misaki shorthand)
A = eɪ  (hey)    I = aɪ  (high)    W = aʊ  (how)    Y = ɔɪ  (soy)

## American-only
æ  ash        O = oʊ  (go)      ᵻ  reduced ɪ/ə (boxes)    ɾ  flap-t (butter)

## British-only
a  ash (Brit)  Q = əʊ  (go-Brit)  ɒ  on             ː  vowel extender

## Custom
ᵊ  small schwa (pixel => pˈɪksᵊl)

## Noun=/s/ vs verb=/z/ pairs (very common TTS error)
use     noun: jus           | verb: juz
house   noun: hWs           | verb: hWz
abuse   noun: əbjˈus        | verb: əbjˈuz
excuse  noun: ɪkskjˈus      | verb: ɪkskjˈuz
close   adj(nearby): klOs   | verb(shut): klOz
refuse  noun(garbage): ɹˈɛfjus | verb(decline): ɹɪfjˈuz

## Vowel-change heteronyms
read  verb-present: ɹid  |  verb-past: ɹɛd
lead  verb: lid           |  noun(metal)/past: lɛd
tear  noun(eye): tɪɹ      |  verb(rip): tɛɹ
live  verb: lɪv           |  adj(broadcast): lIv
wind  noun(breeze): wɪnd  |  verb(coil): wInd
bow   noun(ribbon): bO    |  verb(bend)/ship: bW
bass  music: bAs          |  fish: bæs
minute noun(time): mˈɪnᵻt | adj(tiny): mInjˈut

## Stress-shift noun→verb pairs  (NOUN = first syllable, VERB = second)
present  noun/adj: pɹˈɛzᵻnt   | verb: pɹɪzˈɛnt
record   noun: ɹˈɛkɹd          | verb: ɹɪkˈɔɹd
produce  noun: pɹˈOdus         | verb: pɹᵻdˈus
protest  noun: pɹˈOtɛst        | verb: pɹətˈɛst
progress noun: pɹˈɑɡɹᵻs        | verb: pɹəɡɹˈɛs
rebel    noun: ɹˈɛbᵻl           | verb: ɹɪbˈɛl
subject  noun/adj: sˈʌbʤᵻkt    | verb: səbʤˈɛkt
suspect  noun/adj: sˈʌspᵻkt    | verb: səspˈɛkt
conflict noun: kˈɑnflɪkt        | verb: kənflˈɪkt
contract noun: kˈɑntɹækt        | verb: kəntɹˈækt
contrast noun: kˈɑntɹæst        | verb: kəntɹˈæst
convert  noun: kˈɑnvɜɹt         | verb: kənvˈɜɹt
convict  noun: kˈɑnvɪkt         | verb: kənvˈɪkt
export   noun: ˈɛkspOɹt         | verb: ɛkspˈOɹt
import   noun: ˈɪmpOɹt          | verb: ɪmpˈOɹt
insert   noun: ˈɪnsɜɹt          | verb: ɪnsˈɜɹt
insult   noun: ˈɪnsʌlt          | verb: ɪnsˈʌlt
transfer noun: tɹˈænsfɜɹ        | verb: tɹænsfˈɜɹ
survey   noun: sˈɜɹvA           | verb: sɜɹvˈA
escort   noun: ˈɛskOɹt          | verb: ɪskˈOɹt
object   noun: ˈɑbʤɛkt          | verb: əbʤˈɛkt
permit   noun: pˈɜɹmᵻt          | verb: pɜɹmˈɪt
conduct  noun: kˈɑndʌkt          | verb: kəndˈʌkt

## -ate suffix  (noun/adj = reduced /ɪt/, verb = full /eɪt/)
graduate  noun/adj: ɡɹˈæʤuᵻt  | verb: ɡɹˈæʤuAt
separate  noun/adj: sˈɛpɹᵻt    | verb: sˈɛpɹAt
moderate  noun/adj: mˈɑdɹᵻt    | verb: mˈɑdɹAt
estimate  noun: ˈɛstᵻmᵻt        | verb: ˈɛstᵻmAt
advocate  noun: ˈædvᵻkᵻt        | verb: ˈædvᵻkAt
delegate  noun: dˈɛlᵻɡᵻt        | verb: dˈɛlᵻɡAt
elaborate adj: ɪlˈæbɹᵻt          | verb: ɪlˈæbɹAt

## -ed suffix  (verb past tense = 1 syllable, adjective = 2 syllables)
aged      verb: Ajd              | adj(elderly): ˈAjᵻd
blessed   verb: blɛst            | adj(holy): blˈɛsᵻd
learned   verb: lɜɹnd            | adj(scholarly): lˈɜɹnᵻd
dogged    verb: dˈɑɡd            | adj(tenacious): dˈɑɡᵻd
beloved   verb: bɪlˈʌvd          | adj(literary): bɪlˈʌvᵻd
"""

def show_key():
    out.p(MISAKI_KEY)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog='kokoro-phonemize',
        description='Misaki pronunciation lookup and annotation for kokoro-tts.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  kp lead                            All pronunciations of "lead"
  kp "word1" "word2"                 Each word looked up individually
  kp "sentence"                      Heteronyms only (to reduce default output)
  kp "sentence" -A (or --all)        Force ALL words/phrases: pronunciations + POS
  kp "sentence" -H                   Heteronyms only
  kp "sentence" --all -H             All heteronym variants, POS shown
  kp "I want a [dog]"                Bracket = request pronunciation
  kp "The [dog] won a contest." -H   Brackets imply -H for the rest
  kp "sentence" --annotate           Output with [word](/phonemes/) inline
  kp --list                          Educational heteronym reference
  kp --key                           Paste-ready Misaki guide for LLMs
  kp --key --cb                      Same, copied to clipboard
  kp "sentence" --cb                 Output + copy to clipboard
  kp "sentence" -C                   Disable colour
        """
    )
    parser.add_argument('words', nargs='*',
        help='One or more words, or a sentence (with optional [bracketed] words).')
    parser.add_argument('--all', '-A', action='store_true',
        help='Show all words with POS and all pronunciations (not just heteronyms).')
    parser.add_argument('--heteronyms', '-H', action='store_true',
        help='Heteronyms only. With --all shows all variants of each heteronym.')
    parser.add_argument('--annotate', '-a', action='store_true',
        help='Output sentence with [word](/phonemes/) annotations inserted.')
    parser.add_argument('--list', '-l', action='store_true',
        help='List all known heteronyms with definitions and examples.')
    parser.add_argument('--key', action='store_true',
        help='Output a paste-ready Misaki phoneme guide (for LLM context).')
    parser.add_argument('--keycb', action='store_true',
        help='Shortcut for --key --cb.')
    parser.add_argument('--cb', action='store_true',
        help='Copy output to clipboard (requires pyperclip).')
    parser.add_argument('--no-color', '-C', action='store_true',
        help='Disable colour output.')
    args = parser.parse_args()

    # Colour
    if args.no_color:
        disable_color()

    # Clipboard
    use_cb = args.cb or args.keycb
    if use_cb:
        if args.all and not args.key and not args.keycb:
            out.warn('Using --all with --cb: full pronunciation dump will be copied to clipboard.')
        out.enable_clipboard()

    # --key / --keycb
    if args.key or args.keycb:
        show_key()
        out.flush()
        return

    # --list
    if args.list:
        show_list()
        out.flush()
        return

    if not args.words:
        parser.print_help()
        return

    # Multiple single-word args
    if len(args.words) > 1 and all(len(w.split()) == 1 for w in args.words):
        for word in args.words:
            show_word(word)
        out.flush()
        return

    # Single word (no spaces, no brackets)
    text = args.words[0] if len(args.words) == 1 else ' '.join(args.words)
    text = text.strip()
    bracketed = _extract_bracketed(text)
    clean_words = _strip_brackets(text).split()

    if len(clean_words) == 1 and not bracketed:
        show_word(text)
    else:
        show_sentence(
            text,
            heteronyms_only=args.heteronyms,
            show_all=args.all,
            annotate=args.annotate,
        )

    out.flush()
    print()


if __name__ == '__main__':
    main()
