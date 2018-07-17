class MatrixBotModule:
    @staticmethod
    def create(cls, config):
        raise NotImplementedError()

    def __init__(self, config):
        self.config = config

    def process(self, client, event):
        raise NotImplementedError()
