from musical_genres_rag.Renderer import EntityRenderer
from musical_genres_rag.Vectorizer import Vectorizer

class Embedder():

    def __init__(self, entity):
        self.entity = entity

    def embed(self):
        pass

    """What did the embedding, as a run records it beside the engine that produced it.

    The class name for the ones that embed with no model of their own, so what has already been
    stored as "TextEmbedder" keeps being read back as the very same thing.
    """
    @classmethod
    def getModelName(cls):
        return cls.__name__

class TextEmbedder(Embedder):

    def embed(self):
        renderer = EntityRenderer(self.entity)
        return renderer.render()

"""The genre as prose, as the vector an index is searched by.

Rendered apart from what the text engine indexes: a word index is unharmed by the keys and the ids,
a pooled vector is diluted by them.
"""
class VectorEmbedder(Embedder):

    def embed(self):
        renderer = EntityRenderer(self.entity)
        return Vectorizer.getShared().encodeDocument(renderer.render('prose'))

    @classmethod
    def getModelName(cls):
        return Vectorizer.getModelName()
