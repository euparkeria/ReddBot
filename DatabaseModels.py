
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class SrsUser(Base):
    __tablename__ = 'srsusers'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String)
    subreddit = Column(String)
    reddit_id = Column(String, unique=True)
    last_check_date = Column(String)
    srs_karma_balance = Column(Integer)
    invasion_number = Column(Integer)


class BotQuotes(Base):
    __tablename__ = 'botquotes'
    id = Column(Integer, primary_key=True, autoincrement=True)
    quote = Column(String)
    author = Column(String)
    usedcount = Column(Integer)


class BotKeywords(Base):
    __tablename__ = 'botkeywords'
    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(String)


class BotReplies(Base):
    __tablename__ = 'botreplies'
    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String)
    author = Column(String)
    thread = Column(String)


class SrsSubreddits(Base):
    __tablename__ = 'srssubreddits'
    id = Column(Integer, primary_key=True, autoincrement=True)
    subreddit = Column(String)
