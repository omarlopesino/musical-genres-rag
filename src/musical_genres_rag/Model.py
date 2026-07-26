class BaseModel():

    def __init__(self, id, name, description):
        self.id = id
        self.name = name
        self.description = description

    def getId(self):
        return self.id
    
    def getName(self):
        return self.name

    def getDescription(self):
        return self.description

class Genre(BaseModel):

    def __init__(self, id, name, description):
        super().__init__(id, name, description)
        self.parents = []
        self.instruments = []
    
    def setInstruments(self, instruments):
        self.instruments = instruments

    def setParents(self, parents):
        self.parents = parents

    def getInstruments(self):
        return self.instruments

    def getParents(self):
        return self.parents

    def getParents(self):
        return self.parents

class Instrument(BaseModel):
    pass
