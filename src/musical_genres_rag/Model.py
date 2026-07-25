class Genre():

    def __init__(self, id, name, description):
        self.id = id
        self.name = name
        self.description = description
    
    def setInstruments(self, instruments):
        self.instruments = instruments

    def setParents(self, parents):
        self.parents = parents

    def getId(self):
        return self.id

class Instrument():
    def __init__(self, id, name, description):
        self.id = id
        self.name = name
        self.description = description
