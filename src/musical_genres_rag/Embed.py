from musical_genres_rag.Renderer import EntityRenderer

class Embedder():

    def __init__(self, entity):
        self.entity = entity

    def embed(self):
        pass

class TextEmbedder(Embedder):

    def embed(self):
        renderer = EntityRenderer(self.entity)
        return renderer.render()

class VectorEmbedder(TextEmbedder):

    def embed(self):
        # @todo inherit text embedder and then vectorize it
        pass