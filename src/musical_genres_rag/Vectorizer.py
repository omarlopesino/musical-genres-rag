from django.conf import settings
from pathlib import Path

import os
import shutil
import threading

# The model, as it is named on the hub, which is also what an evaluation records as its embedding model
MODEL_REPOSITORY = 'Xenova/all-MiniLM-L6-v2'

# How wide a vector it returns, which is what the column it is written to was declared as
VECTOR_DIMENSIONS = 384

MODEL_FILE = 'model.onnx'
TOKENIZER_FILE = 'tokenizer.json'

# Where the graph is kept in a repository, which is not the same place in every one of them
MODEL_CANDIDATES = ['onnx/model.onnx', 'onnx/encoder_model.onnx', MODEL_FILE]

# Weights too large to travel inside the graph are published beside it under this suffix, and are
# read back by the name the graph refers to them as
WEIGHTS_SUFFIX = '_data'

"""How much of a document the model reads.

Said here rather than left to the tokenizer file, which ships a truncation of its own at 128 tokens:
half of what this model was trained to read, and a small fraction of a rendered genre. What is cut
is cut from the end, where the renderer emits the parents and the instruments, so the name and the
description of the entity always reach the model.
"""
MAX_TOKENS = 256

MISSING = (
    'The embedding model is not downloaded: "{path}" is not there. '
    'Run "make downloadModel" before indexing or searching with a vector engine.'
)

NO_GRAPH = 'The repository "{repository}" publishes no ONNX graph under any of {candidates}.'

"""Where the weights are read from: a directory per model, under the one the settings name"""
def getModelDirectory():
    return Path(settings.MODELS_DIRECTORY) / MODEL_REPOSITORY

"""Turns text into the vector an index is written and searched by.

One session for the whole process. SearchEngine builds an embedder per entity, and a session is
ninety megabytes of weights read off disk and a graph optimised over them, so an embedder that built
its own would pay for that once per genre indexed. A session is safe to run from several threads,
which is what lets a background task and a request share this one.
"""
class Vectorizer:

    shared = None
    lock = threading.Lock()

    """The session of this process, built the first time anything asks for it.

    Locked, and checked again inside the lock, because an operation runs in a thread of its own: two
    arriving together would otherwise each load the weights, and only one of them would be kept.
    """
    @classmethod
    def getShared(cls):
        if cls.shared is None:
            with cls.lock:
                if cls.shared is None:
                    cls.shared = cls()

        return cls.shared

    """What embedded a document, as a run records it beside the engine that produced it"""
    @classmethod
    def getModelName(cls):
        return MODEL_REPOSITORY

    def __init__(self, directory = None):
        # Imported here rather than at the top of the file, so a process that never embeds anything
        # neither loads onnxruntime nor needs the weights to be on disk at all
        import numpy
        import onnxruntime

        from tokenizers import Tokenizer

        self.numpy = numpy
        directory = directory if directory is not None else getModelDirectory()

        self.tokenizer = Tokenizer.from_file(str(self._require(directory / TOKENIZER_FILE)))
        self.tokenizer.enable_truncation(max_length = MAX_TOKENS)
        self.tokenizer.enable_padding()
        self.session = onnxruntime.InferenceSession(
            str(self._require(directory / MODEL_FILE)),
            providers = ['CPUExecutionProvider'],
        )
        self.inputs = {input.name for input in self.session.get_inputs()}

    """One text, as the literal a vector column is written and searched by"""
    def encode(self, text):
        [vector] = self.encodeMultiple([text])

        return vector

    def encodeMultiple(self, texts):
        return [self._toLiteral(vector) for vector in self._pool(texts)]

    """Mean pooling over the tokens that are not padding, brought to unit length.

    Unit length is what makes the cosine distance the index is built on the same ordering as the dot
    product, and what keeps two documents of different lengths comparable at all.
    """
    def _pool(self, texts):
        encoded = self.tokenizer.encode_batch(texts)
        feed = {
            'input_ids': self._toArray([one.ids for one in encoded]),
            'attention_mask': self._toArray([one.attention_mask for one in encoded]),
            'token_type_ids': self._toArray([one.type_ids for one in encoded]),
        }
        # Only what this graph declares: the same model is published with and without the segments
        feed = {name: value for name, value in feed.items() if name in self.inputs}

        [hidden, *rest] = self.session.run(None, feed)
        mask = feed['attention_mask'][..., None]
        pooled = (hidden * mask).sum(axis = 1) / mask.sum(axis = 1)

        return pooled / self.numpy.linalg.norm(pooled, axis = 1, keepdims = True)

    def _toArray(self, rows):
        return self.numpy.array(rows, dtype = self.numpy.int64)

    """A vector as pgvector reads one, which is a text literal cast on its way into the query.

    Written here rather than handed over as a list of numbers, because what comes out of a session
    are numpy floats, which psycopg has no dumper for, and because a literal needs nothing
    registered on the connection to be understood.
    """
    def _toLiteral(self, vector):
        return '[' + ','.join(str(float(value)) for value in vector) + ']'

    """The path, or what to run to have it"""
    def _require(self, path):
        if not path.exists():
            raise FileNotFoundError(MISSING.format(path = path))

        return path

"""Fetches the weights the vectorizer reads, once per clone.

Two files out of a repository that holds every format the model was published in, stored flat under
the names the vectorizer looks for rather than as the hub lays them out.
"""
class VectorizerDownload:

    def __init__(self, repository = MODEL_REPOSITORY, directory = None):
        self.repository = repository
        self.directory = Path(directory) if directory is not None else getModelDirectory()

    """Every file the vectorizer needs, against whether this run is what put it there"""
    def download(self):
        # Nothing is reported to the hub about a download that only ever fetches two known files
        os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')

        from huggingface_hub import hf_hub_download, list_repo_files

        published = list_repo_files(repo_id = self.repository)
        self.directory.mkdir(parents = True, exist_ok = True)

        downloaded = {}
        for remote, local in self._getFiles(published).items():
            path = self.directory / local
            downloaded[path] = not path.exists()
            if downloaded[path]:
                # Copied out of the hub's cache rather than linked, so nothing here breaks when
                # whoever owns that cache empties it
                shutil.copy2(hf_hub_download(repo_id = self.repository, filename = remote), path)

        return downloaded

    """What to fetch, as the name it is published under against the name it is stored as"""
    def _getFiles(self, published):
        graph = next((candidate for candidate in MODEL_CANDIDATES if candidate in published), None)
        if graph is None:
            raise FileNotFoundError(NO_GRAPH.format(
                repository = self.repository,
                candidates = ', '.join(MODEL_CANDIDATES),
            ))

        files = {TOKENIZER_FILE: TOKENIZER_FILE, graph: MODEL_FILE}
        if graph + WEIGHTS_SUFFIX in published:
            files[graph + WEIGHTS_SUFFIX] = MODEL_FILE + WEIGHTS_SUFFIX

        return files
