import os

CUR_DIR = os.path.dirname(__file__)
RESOURCES_DIR = os.path.join(CUR_DIR, "resources")


class ObjectView(object):
    def __init__(self, d):
        self.__dict__ = d
