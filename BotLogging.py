import logging


'''
logging configguration
'''
BotLogger = logging.getLogger('ReddBot')
BotLogger.setLevel(logging.DEBUG)

nicelogformat = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(message)s',
                                  datefmt='%m/%d %I:%M')

ConsoleHandler = logging.StreamHandler()
ConsoleHandler.setLevel(logging.INFO)
ConsoleHandler.setFormatter(nicelogformat)

FileHandler = logging.FileHandler(filename='log.txt')
FileHandler.setLevel(logging.WARNING)
FileHandler.setFormatter(nicelogformat)


BotLogger.addHandler(ConsoleHandler)
BotLogger.addHandler(FileHandler)
