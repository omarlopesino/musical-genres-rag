from django.conf import settings

import threading
import yaml

MISSING_FILE = (
    'The configuration is not there: "{path}" does not exist. '
    'Run "make config" to copy it from config.yml.dist.'
)

MISSING_KEY = 'The configuration file "{path}" says nothing under "{key}", which is required to run.'

"""Where the prompts under a section are read from, so a prompt is named by what it is for"""
PROMPTS = 'prompts'

"""What decides how this application behaves, read from the file rather than written in the code.

The prompts, the models and the engine live in config.yml so that tuning any of them is editing a
file rather than editing Python. Whatever it says is the only thing said: nothing here defaults a
value the file also carries, so the two can never drift apart and a key left out is an error rather
than a silent fallback to something nobody wrote down.
"""
class Config:

    """One document for the whole process.

    The file is small, but a request answered through the API and a task running in a thread beside
    it would otherwise each parse their own, and a prompt would be read from disk once per call.
    """
    shared = None
    lock = threading.Lock()

    @classmethod
    def getShared(cls):
        if cls.shared is None:
            with cls.lock:
                if cls.shared is None:
                    cls.shared = cls(settings.CONFIG_FILE)

        return cls.shared

    def __init__(self, path):
        self.path = path
        self.document = self._load(path)

    """Which search engine everything runs through unless a run is told another one"""
    def getIndexEngine(self):
        return self._read('index_engine')

    """The model that writes an answer, generates the ground truth and judges both"""
    def getChatModel(self):
        return self._read('models.chat')

    """The embedding model, named as the hub names it, which is also how a run records it"""
    def getEmbeddingModel(self):
        return self._read('models.embedding')

    """One prompt, by where it sits under "prompts": "rag.instructions", "evaluation.judge.rubric".

    Stripped on the way out, so how a block is laid out in the file is never what reaches the model.
    """
    def getPrompt(self, path):
        return self._read('{section}.{path}'.format(section = PROMPTS, path = path)).strip()

    """Reads a value by the dotted path it sits at, naming what is missing rather than raising over
    whichever half of the path ran out"""
    def _read(self, key):
        value = self.document
        for step in key.split('.'):
            if not isinstance(value, dict) or step not in value:
                raise Exception(MISSING_KEY.format(path = self.path, key = key))
            value = value[step]

        return value

    def _load(self, path):
        try:
            with open(path) as file:
                return yaml.safe_load(file) or {}
        except FileNotFoundError:
            raise Exception(MISSING_FILE.format(path = path))
