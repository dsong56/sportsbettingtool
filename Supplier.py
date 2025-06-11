class Supplier:
    def __init__(self):
        # The key is the API key for the-odds-api at https://the-odds-api.com/#get-access
        self.key = "b05d3b0d573eebd52438cb70d9a971e6"
        
        # The directory is the location of the projections.json file
        self.directory = "c:\\Users\\epicy\\Downloads\\projections.json"
        
    def get_key(self):
        return self.key
    
    def get_directory(self):
        return self.directory