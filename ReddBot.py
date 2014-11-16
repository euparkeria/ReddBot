import threading
import time
from imgurpython.helpers.error import ImgurClientRateLimitError, ImgurClientError
import praw
import json
import os
import pickle
import re
from ggplot import *
from pandas import DataFrame
from random import choice
from praw.errors import APIException, ClientException
from requests import exceptions
from twython import Twython
from twython import TwythonError
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import sessionmaker
from imgurpython import ImgurClient


watched_subreddit = "+".join(['all'])
results_limit = 2000
results_limit_comm = 900
bot_agent_name = 'antibrigadebot 2.0 /u/antibrigadebot2'
loop_timer = 60
secondary_timer = loop_timer * 5
DEBUG_LEVEL = 1
CACHEFILE = 'reddbot.cache'
AUTHFILE = 'ReddAUTH.json'
DATAFILE = 'ReddDATA.json'

engine = create_engine('sqlite:///ReddDatabase.db')
Base = declarative_base()
DBSession = sessionmaker(bind=engine)


class UsernameBank:
    def __init__(self):
        self.reddit_username = ""  # currently logged on with username
        self.username_count = len(botconfig.bot_auth_info['REDDIT_BOT_USERNAME'])
        self.already_tried = []
        self.defaut_username = botconfig.bot_auth_info['REDDIT_BOT_USERNAME'][0]  # first username is default
        self.prev_username = ''  # previous used username

    def get_username(self, exclude=''):
        if not exclude:
            exclude = self.reddit_username
        self.already_tried.append(exclude)

        new_random_username = choice([x for x in botconfig.bot_auth_info['REDDIT_BOT_USERNAME']
                                      if x is not exclude and x not in self.already_tried])
        if new_random_username:
            self.already_tried.append(new_random_username)
            return new_random_username
        else:
            return self.defaut_username

    def purge_tried_list(self):
        self.already_tried = []

    def prev_username_login(self):
        if self.reddit_username != self.prev_username:
            reddit_operations.login(username_bank.prev_username)
            self.prev_username = ''


class SrsUser(Base):
    __tablename__ = 'SrsUsers'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String)
    subreddit = Column(String)
    reddit_id = Column(String, unique=True)
    last_check_date = Column(String)
    SRS_karma_balance = Column(Integer)
    invasion_number = Column(Integer)


class MaintThread(threading.Thread):
    def __init__(self, threadid, name, counter):
        threading.Thread.__init__(self)
        self.threadID = threadid
        self.name = name
        self.counter = counter

    def run(self):
        print("Starting " + self.name)
        botconfig.check_for_updated_config()
        WatchedTreads.update_all()


class SocialMedia:
    def __init__(self):
        self.reddit_session = self.connect_to_reddit()
        self.twitter_session = self.connect_to_twitter()
        self.imgur_client = self.connect_to_imgur()

    @staticmethod
    def connect_to_reddit():
        r = praw.Reddit(user_agent=bot_agent_name, api_request_delay=1)
        return r

    @staticmethod
    def connect_to_twitter():
        try:
            t = Twython(botconfig.bot_auth_info['APP_KEY'],
                        botconfig.bot_auth_info['APP_SECRET'],
                        botconfig.bot_auth_info['OAUTH_TOKEN'],
                        botconfig.bot_auth_info['OAUTH_TOKEN_SECRET'])
        except TwythonError:
            log_this('ERROR: Cant authenticate into twitter')
        return t

    @staticmethod
    def connect_to_imgur():
        imgur_client = ImgurClient(botconfig.bot_auth_info['IMGUR_CLIENT_ID'],
                                   botconfig.bot_auth_info['IMGUR_CLIENT_SECRET'])
        return imgur_client


class ConfigFiles:
    def __init__(self):
        self.data_modified_time = 0
        cache = self.loadcache()
        if cache:
            WatchedTreads.watched_threads_list = cache

        self.redd_data = None
        self.bot_auth_info = None
        self.check_for_updated_config()

    def check_for_updated_config(self):
        if os.stat(DATAFILE).st_mtime > self.data_modified_time:
            self.redd_data = self.readdatafile()
            self.bot_auth_info = self.readauthfile()
            debug('CONFIG FILES RELOADED!')
            return True

    @staticmethod
    def readauthfile():
        with open(AUTHFILE, 'r', encoding='utf-8') as f:
            bot_auth_info = json.load(f)
        return bot_auth_info

    @staticmethod
    def loadcache():
        try:
            with open(CACHEFILE, 'rb') as f:
                return pickle.load(f)
        except IOError:
            debug('Cache File not Pressent')
            return False

    def readdatafile(self):
        try:
            self.data_modified_time = os.stat(DATAFILE).st_mtime
            with open(DATAFILE, 'r', encoding='utf-8') as f:
                redd_data = json.load(f)
                redd_data['KEYWORDS'] = sorted(redd_data['KEYWORDS'], key=len, reverse=True)
                redd_data['SRSs'] = [x.lower() for x in redd_data['SRSs']]
                #redd_data['quotes'] = [''.join(('^', x.replace(" ", " ^"))) for x in redd_data['quotes']]
        except IOError:
            log_this("Error reading data file")
        return redd_data


class QuoteBank:
    def __init__(self):
        self.quotes_matched = {}
        self.keyword_matched = False

    @staticmethod
    def lcs(s1, s2):
        m = [[0] * (len(s2) + 1) for i in range(len(s1) + 1)]
        longest, x_longest = 0, 0
        for x in range(1, len(s1) + 1):
            for y in range(1, len(s2) + 1):
                if s1[x - 1] == s2[y - 1]:
                    m[x][y] = m[x - 1][y - 1] + 1
                    if m[x][y] > longest:
                        longest = m[x][y]
                        x_longest = x
                else:
                    m[x][y] = 0
        return s1[x_longest - longest: x_longest]

    @staticmethod
    def remove_punctuation(quote):
        punctuation = "!\"#$%&'()*+,-.:;<=>?@[\\]^_`{|}~"
        punct_clear = ""
        for letter in quote:
            if letter not in punctuation:
                punct_clear += letter
        #return punct_clear.split()
        return punct_clear

    def get_quote(self, quotes, topicname):
        topicname = self.remove_punctuation(topicname.lower())
        for quote in quotes:
            q = self.remove_punctuation(quote.lower())
            match = self.lcs(topicname, q)

            if match:
                match = [x for x in match.split() if len(x) > 2]  # list of words of the match that are > 2 characters
                if match and len(max(match, key=len)) >= 6:  # if there is a word of at least 6 characters
                    match = ' '.join(match)
                    for keyword in botconfig.redd_data['KEYWORDS']:
                        if self.lcs(keyword.lower(), match.lower()) in botconfig.redd_data['KEYWORDS']:
                            self.quotes_matched[keyword + "-KEYWORD{:.>5}".format(quotes.index(quote))] = quote
                            self.keyword_matched = True
                    if not self.keyword_matched:
                        self.quotes_matched[match + "{:.>5}".format(quotes.index(quote))] = quote

        if self.quotes_matched:
            keys = list(self.quotes_matched.keys())

            if self.keyword_matched:
                keyword_matches_keys = [key for key in keys if '-KEYWORD' in key]
                log_this(keyword_matches_keys)
                quote_to_return = self.quotes_matched[choice(keyword_matches_keys)]
            else:
                longest_keys = [key for key in keys if len(key) >= len(max(keys, key=len)) - 1]  # all longest
                log_this(longest_keys)
                quote_to_return = self.quotes_matched[choice(longest_keys)]

        else:
            quote_to_return = choice(quotes)
        return ''.join(('^', quote_to_return.replace(" ", " ^")))


class RedditOperations:
    """Contains reddit, twitter and imgur api related operations"""

    def __init__(self):
        self.socmedia = SocialMedia()

    def upload_image(self, image_path):
        try:
            image_object = self.socmedia.imgur_client.upload_from_path(path=image_path)
        except (ImgurClientRateLimitError, ImgurClientError):
            debug('ERROR: Imgur Rate Limit Exceeded')
            return False
        return image_object

    def login(self, username=''):
        try:
            if not username:
                username = username_bank.get_username()
            self.socmedia.reddit_session.login(username, botconfig.bot_auth_info['REDDIT_BOT_PASSWORD'])
            username_bank.reddit_username = username
            debug('Sucessfully logged in as {0}'.format(username_bank.reddit_username))
            time.sleep(3)
        except praw.errors.APIException:
            log_this('ERROR: Cant login to Reddit.com')

    def get_post_attribute(self, url, attribute):
        """returns a post attribute as a string"""
        value = None
        try:
            post = self.socmedia.reddit_session.get_submission(url=url)
            is_comment = reddit_operations.submission_or_comment(url)
            if is_comment:
                value = getattr(post.comments[0], attribute)
            elif not is_comment:
                value = getattr(post, attribute)
        except (APIException,
                ClientException,
                praw.requests.exceptions.HTTPError,
                praw.requests.exceptions.ConnectionError):
            debug("Error: Couldnt get post score")
        debug("NB {}".format(value))
        return str(value)

    @staticmethod
    def submission_or_comment(url):
        """Returns True if url is Comment and False if Submission
        redo with hasattr
        """
        """"""
        result_url = [x for x in url.split('/') if len(x)]
        if len(result_url) == 7:
            return False
        elif len(result_url) == 8:
            return True

    def get_user_karma_balance(self, author, in_subreddit, user_comments_limit=200):
        user_srs_karma_balance = 0

        try:
            user = self.socmedia.reddit_session.get_redditor(author)
            for usercomment in user.get_overview(limit=user_comments_limit):
                if str(usercomment.subreddit) == in_subreddit:
                    user_srs_karma_balance += usercomment.score
        except (APIException, ClientException):
            log_this('ERROR: Cant get user SRS karma balance!!')
        return user_srs_karma_balance

    def get_authors_in_thread(self, thread):
        authors_list = []
        try:
            submission = self.socmedia.reddit_session.get_submission(thread)
            submission.replace_more_comments(limit=4, threshold=1)
            for comment in praw.helpers.flatten_tree(submission.comments):
                author = str(comment.author)
                if author not in botconfig.bot_auth_info['REDDIT_BOT_USERNAME']:
                    authors_list.append(author)
        except (APIException, praw.requests.exceptions.HTTPError, praw.requests.exceptions.ConnectionError):
            log_this('ERROR:couldnt get all authors from thread')
        return authors_list

    def edit_comment(self, comment_id, comment_body, poster_username):
        username_bank.prev_username = username_bank.reddit_username
        if username_bank.reddit_username != poster_username:
            self.login(poster_username)
        try:
            comment = self.socmedia.reddit_session.get_info(thing_id=comment_id)
            comment.edit(comment_body)
            debug('Comment : {} edited.'.format(comment_id))
            username_bank.prev_username_login()
        except (APIException, praw.requests.exceptions.HTTPError, praw.requests.exceptions.ConnectionError):
            log_this('ERROR: Cant edit comment')

    def get_comments_or_subs(self, placeholder_id='', subreddit=watched_subreddit,
                             limit=results_limit, target='submissions'):
        if target == 'submissions':
            return self.socmedia.reddit_session.get_subreddit(subreddit).get_new(limit=limit,
                                                                                 place_holder=placeholder_id)
        if target == 'comments':
            return self.socmedia.reddit_session.get_comments(subreddit, limit=limit)

    def comment_to_url(self, obj, msg, result_url):
        """hacky"""
        is_comment = reddit_operations.submission_or_comment(result_url)
        return_obj = None
        retry_attemts = username_bank.username_count
        username_bank.prev_username = username_bank.reddit_username

        for retry in range(retry_attemts):
            try:
                if not is_comment:
                    return_obj = obj.add_comment(msg)
                    debug('NOTICE ADDED to ID:{0}'.format(obj.id))
                    break
                elif is_comment:
                    return_obj = obj.comments[0].reply(msg)
                    debug('NOTICE REPLIED to ID:{0}'.format(obj.comments[0].id))
                    break
            except (praw.errors.APIException,
                    praw.requests.exceptions.HTTPError,
                    praw.requests.exceptions.ConnectionError):
                log_this('{1} is BANNED in:{0}, trying to relog'.format(obj.subreddit, username_bank.reddit_username))
                self.login()

        username_bank.prev_username_login()
        username_bank.purge_tried_list()
        return return_obj

    def get_submission_by_url(self, url):
        return self.socmedia.reddit_session.get_submission(url)

    def send_pm_to_owner(self, pm_text):
        try:
            self.socmedia.reddit_session.user.send_message(botconfig.bot_auth_info['REDDIT_PM_TO'], pm_text)
        except (APIException, praw.requests.exceptions.HTTPError, praw.requests.exceptions.ConnectionError):
            log_this('ERROR:Cant send pm')

    @staticmethod
    def make_np(link):
        return link.replace('http://www.reddit.com', 'http://np.reddit.com')

    def tweet_this(self, msg):
        if len(msg) > 140:
            msg = msg[:139]
            log_this('MSG exceeding 140 characters!!')
        try:
            self.socmedia.twitter_session.update_status(status=msg)
            debug('TWEET SENT!!!')
        except TwythonError:
            log_this('ERROR: couldnt update twitter status')


class WatchedTreads:
    watched_threads_list = []

    def __init__(self, thread_url, srs_subreddit, srs_author, bot_reply_object_id, bot_reply_body, poster_username):
        self.thread_url = thread_url
        self.srs_subreddit = srs_subreddit
        self.srs_author = srs_author
        self.start_watch_time = time.time()
        self.already_processed_users = []
        self.bot_reply_object_id = bot_reply_object_id
        self.bot_body = bot_reply_body
        self.poster_username = poster_username
        self.keep_alive = 43200  # time to watch a thread in seconds
        self.graph_image_link = ''
        self.last_parent_post_score = reddit_operations.get_post_attribute(url=self.thread_url, attribute='score')
        self.parent_post_author = reddit_operations.get_post_attribute(url=self.thread_url, attribute='author')
        self.GraphData = DataFrame(data=[(0, self.last_parent_post_score)],
                                   columns=['Min', 'Score'])

        WatchedTreads.watched_threads_list.append(self)

        self.draw_graph()
        self.savecache()

    def draw_graph(self):
        filename = '{}.png'.format(self.bot_reply_object_id)

        p = ggplot(aes(x='Min', y='Score'), data=self.GraphData, ) +\
            geom_point(color='red', size=20) +\
            geom_line(colour="pink") +\
            theme_seaborn(context='paper') +\
            stat_smooth(colour='magenta') +\
            scale_y_continuous("{}'s post Karma".format(self.parent_post_author)) +\
            scale_x_continuous("Minutes since the brigade began") +\
            labs(title="Brigade Effect Graph") +\
            xlim(0)

        ggsave(p, filename, width=8, height=5, dpi=100, scale=1)
        return filename

    @staticmethod
    def savecache():
        try:
            with open(CACHEFILE, 'wb') as fa:
                pickle.dump(WatchedTreads.watched_threads_list, fa)
        except IOError:
            log_this('ERROR: Cant write cache file')

    @staticmethod
    def add_user_to_database(username, subreddit, srs_karma):
        session = DBSession()

        if not WatchedTreads.check_if_already_in_db(username, subreddit):
            stupiduser = SrsUser(username=username,
                                 subreddit=subreddit,
                                 last_check_date=time.time(),
                                 SRS_karma_balance=srs_karma)
            session.add(stupiduser)

            debug("{} Added to database!".format(username))
        else:
            users_query = session.query(SrsUser).filter_by(username=username, subreddit=subreddit).first()
            if users_query.invasion_number:
                users_query.invasion_number += 1
            else:
                users_query.invasion_number = 1
            users_query.last_check_date = time.time()
            users_query.SRS_karma_balance = srs_karma
            debug("Updated database entry on: {0} !".format(username))
        session.commit()

    @staticmethod
    def check_if_already_in_db(username, subreddit):
        session = DBSession()
        users_query = session.query(SrsUser).filter_by(username=username, subreddit=subreddit)
        if users_query.count():
            return True
        else:
            return False

    def update(self):
        bot_comment_changed = False

        new_invaders_list = self.check_for_new_invaders()

        if new_invaders_list:
            self.bot_body = self.add_user_lines(srs_users=new_invaders_list)
            bot_comment_changed = True

        current_parent_post_score = reddit_operations.get_post_attribute(url=self.thread_url, attribute='score')
        if self.last_parent_post_score is not current_parent_post_score:
            self.last_parent_post_score = current_parent_post_score
            self.update_graph()
            bot_comment_changed = True

        if bot_comment_changed:
            reddit_operations.edit_comment(comment_id=self.bot_reply_object_id,
                                           comment_body=self.bot_body,
                                           poster_username=self.poster_username)

        if self.check_if_expired():
            debug('--Watched Thread Expired and Removed!')

    def check_for_new_invaders(self):
        karma_upper_limit = 3  # if poster has more than that amount of karma in the srs subreddit he is added
        srs_users = []
        debug('Now processing: {}'.format(self.thread_url))

        for author in reddit_operations.get_authors_in_thread(thread=self.thread_url):
            if author not in self.already_processed_users:
                debug('--Checking user: {}'.format(author), end=" ")
                user_srs_karma_balance = reddit_operations.get_user_karma_balance(author=author,
                                                                                  in_subreddit=self.srs_subreddit)
                debug(',/r/{0} karma score:{1} '.format(self.srs_subreddit, user_srs_karma_balance), end=" ")
                if user_srs_karma_balance >= karma_upper_limit:
                    srs_users.append(author)
                    WatchedTreads.add_user_to_database(username=author,
                                                       subreddit=self.srs_subreddit,
                                                       srs_karma=user_srs_karma_balance)
                    debug('MATCH', end=" ")
                debug('.')
                self.already_processed_users.append(author)
        return srs_users

    def update_graph(self):
        self.GraphData.loc[len(self.GraphData)] = [(time.time() - self.start_watch_time)/60,
                                                   self.last_parent_post_score]
        graph_image_name = self.draw_graph()

        imgurl_image = reddit_operations.upload_image(graph_image_name)
        if imgurl_image:
            self.graph_image_link = imgurl_image['link']

            self.bot_body = re.sub('-- \[(.*)] --', '-- [[Karma Graph]({})] --'
                                   .format(self.graph_image_link), self.bot_body)

    @staticmethod
    def update_all():
        debug('Currently Watching {} threads.'.format(len(WatchedTreads.watched_threads_list)))
        for thread in WatchedTreads.watched_threads_list:
            thread.update()
            WatchedTreads.savecache()

    def add_user_lines(self, srs_users):
        split_mark = '\n\n-- ['
        splitted_comment = self.bot_body.split(split_mark, 1)
        srs_users_lines = ''.join(['\n\n* [/u/' + user + '](http://np.reddit.com/u/' + user + ')\n\n'for user in srs_users])
        return splitted_comment[0] + srs_users_lines + split_mark + splitted_comment[1]

    def check_if_expired(self):
            time_watched = time.time() - self.start_watch_time
            debug('--Watched for {} hours'.format(time_watched/60/60))
            if time_watched > self.keep_alive:  # if older than 8 hours
                WatchedTreads.watched_threads_list.remove(self)
                return True


class MatchedSubmissions:

    matching_results = []

    def __init__(self, dsubmission, target, keyword_lists):
        self.args = {'dsubmission': dsubmission, 'target': target, 'keyword_lists': keyword_lists}
        self.body_text = self._get_body_text()
        self.url = self._get_clean_url()

        self.is_srs = False
        self.keyword_matched = ''

        self.msg_for_tweet = None
        self.msg_for_reply = None

        # list of checks on each submissions, functions MUST return True or False
        self.checks = [self._find_matching_keywords(),
                       self._detect_brigade()]  # self._detect_brigade(), self._find_matching_keywords()
        checks_results = [function for function in self.checks]
        if True in checks_results:
            self.link = self._get_link()  # this is slow so gonna be set only for matching results

            msg_functions_list = [self._brigade_message(),
                                  self._brigade_tweet(),
                                  self._keyword_match_tweet()]
            build_messages = [msg_function for msg_function in msg_functions_list]
            if True in build_messages:
                MatchedSubmissions.matching_results.append(self)

    def _get_link(self):
        if self.args['target'] == 'submissions':
            return self.args['dsubmission'].short_link
        if self.args['target'] == 'comments':
            return self.args['dsubmission'].permalink

    def _get_clean_url(self):
        clean_url = re.sub(r'\?(.*)', '', self.args['dsubmission'].url)
        return clean_url

    def _get_body_text(self):
        if self.args['target'] == 'submissions':
            return self.args['dsubmission'].title + self.args['dsubmission'].selftext
        if self.args['target'] == 'comments':
            return self.args['dsubmission'].body

    def _find_matching_keywords(self):
        for keyword in self.args['keyword_lists']['KEYWORDS']:
            if keyword.lower() in self.body_text.lower():
                self.keyword_matched = keyword
                return True
        return False

    def _detect_brigade(self):
        subreddit = str(self.args['dsubmission'].subreddit)
        if subreddit.lower() in self.args['keyword_lists']['SRSs'] and 'reddit.com' in self.url \
                and not self.args['dsubmission'].is_self:
            self.is_srs = True
            return True
        return False

    @staticmethod
    def purge_list():
        MatchedSubmissions.matching_results = []

    def _brigade_message(self):
        """needs to be redone completely"""
        if self.is_srs:
            quote = QuoteBank()
            quote = quote.get_quote(self.args['keyword_lists']['quotes'], self.args['dsubmission'].title)
            submissionlink = reddit_operations.make_np(self.args['dsubmission'].permalink)
            brigade_subreddit_link = '*[/r/{0}]({1})*'.format(self.args['dsubmission'].subreddit, submissionlink)

            greetings = ['Notice']

            updated_on = '^updated ^every ^5 ^minutes ^for ^12 ^hours.'

            members_active = ['Members of {0} active in this thread:{1}'.format(brigade_subreddit_link, updated_on)]

            stars = ['★', '☭']

            their_title = ['Title:']

            explanations = ['This thread has been targeted by a *possible* downvote-brigade from {0}'
                            .format(brigade_subreddit_link),
                            'This post was just linked from {0} in a *possible* attempt to downvote it.'
                            .format(brigade_subreddit_link)
                            ]

            lines = ['#**{0}**:\n'.format(choice(greetings)),
                     '{0}\n\n'.format(choice(explanations)),
                     '**{0}**\n\n'.format(choice(their_title)),
                     '* *[{0}]({1})*\n\n'.format(self.args['dsubmission'].title, submissionlink),
                     '**{0}**\n\n'.format(choice(members_active)),
                     '-- [*Waiting for Karma Graph*] --\n\n'
                     '\n\n-----\n',
                     '^{1} *{0}* ^{1}\n\n'.format(quote, choice(stars)),
                     ]

            self.msg_for_reply = ''.join(lines)
            #  "[^|bot ^twitter ^feed|](https://twitter.com/bot_redd)"\
            return True
        return False

    def _keyword_match_tweet(self):
        if self.keyword_matched and not self.is_srs:
            self.msg_for_tweet = 'Submission regarding #{0} posted in /r/{1} : {2} #reddit'.format(
                self.keyword_matched.replace(' ', '_'), self.args['dsubmission'].subreddit, self.link)
            return True
        return False

    def _brigade_tweet(self):
        if self.is_srs and self.keyword_matched:
            self.msg_for_tweet = 'ATTENTION: possible reactionary brigade from /r/{1} regarding #{0}: {2} #reddit'\
                .format(self.keyword_matched.replace(' ', '_'), self.args['dsubmission'].subreddit, self.link)

            return True
        return False


class ReddBot:

    def __init__(self):
        self.first_run = True
        self.pulllimit = {'submissions': results_limit, 'comments': results_limit_comm}
        self.cont_num = {'comments': 0, 'submissions': 0}
        self.processed_objects = {'comments': [], 'submissions': []}
        self.loops = ['submissions']  # 'submissions' and 'comments' loops
        self.permcounters = {'comments': 0, 'submissions': 0}
        self.twitter = None
        self.placeholder_id = None  # this doesn't always work !? but it will lower the traffic to some extent
        self.mthread = None

        loop_counter = 0
        while True:
            loop_counter += 1
            if loop_counter >= secondary_timer / loop_timer or self.first_run:
                self._maintenance_loop()
                loop_counter = 0

            self._mainlooper()

    def _maintenance_loop(self):
        maint_thread_name = "Maintenance Thread"
        if self.first_run:
            self.mthread = MaintThread(1, maint_thread_name, 1)

        if not self.mthread.isAlive():
                self.mthread = MaintThread(1, maint_thread_name, 1)
                self.mthread.start()

    def _mainlooper(self):

        self.cont_num['submissions'], self.cont_num['comments'] = 0, 0

        for loop in self.loops:
            self._contentloop(target=loop)
            buffer_reset_lenght = self.pulllimit[loop] * 10
            if len(self.processed_objects[loop]) >= buffer_reset_lenght:
                self.processed_objects[loop] = self.processed_objects[loop][int(len(self.processed_objects[loop]) / 2):]
                debug('Buffers LENGHT after trim {0}'.format(len(self.processed_objects[loop])))
            if not self.first_run:
                self.pulllimit[loop] = self._calculate_pull_limit(self.cont_num[loop], target=loop)
            self.permcounters[loop] += self.cont_num[loop]

        debug('{0}th sec. Sub so far:{1},THIS run:{2}.'
              'Comments so far:{3},THIS run:{4}'
              .format(int((time.time() - start_time)), self.permcounters['submissions'],
                      self.cont_num['submissions'], self.permcounters['comments'],
                      self.cont_num['comments']))

        self.first_run = False

        debug(self.pulllimit['submissions'])
        debug(self.pulllimit['comments'])

        time.sleep(loop_timer)

    def _calculate_pull_limit(self, lastpullnum, target):
        """this needs to be done better"""
        add_more = {'submissions': 100, 'comments': 300}   # how many items above last pull number to pull next run

        if lastpullnum == 0:
            lastpullnum = results_limit / 2   # in case no new results are returned

        if self.pulllimit[target] - lastpullnum == 0:
            self.pulllimit[target] *= 2
        else:
            self.pulllimit[target] = lastpullnum + add_more[target]
        return int(self.pulllimit[target])

    def _get_new_comments_or_subs(self, target):
        results = reddit_operations.get_comments_or_subs(placeholder_id=self.placeholder_id,
                                                         subreddit=watched_subreddit,
                                                         limit=self.pulllimit[target],
                                                         target=target)

        new_submissions_list = []
        try:
            for submission in results:
                if submission.id not in self.processed_objects[target]:
                    new_submissions_list.append(submission)
                    self.processed_objects[target].append(submission.id)  # add to list of already processed submission
                    self.cont_num[target] += 1   # count the number of submissions processed each run
            if new_submissions_list:
                self.placeholder_id = new_submissions_list[0].id
        except (praw.errors.APIException, exceptions.HTTPError, exceptions.ConnectionError):
            log_this('ERROR:Cannot connect to reddit!!!')
        return new_submissions_list

    def _contentloop(self, target):
        new_submissions = self._get_new_comments_or_subs(target)

        if new_submissions:

            for new_submission in new_submissions:
                MatchedSubmissions(target=target, dsubmission=new_submission, keyword_lists=botconfig.redd_data)

            if MatchedSubmissions.matching_results:
                self.dispatch_nitifications(results_list=MatchedSubmissions.matching_results)
                MatchedSubmissions.purge_list()

    def dispatch_nitifications(self, results_list):
        for result in results_list:
            if result.msg_for_reply:
                try:
                    targeted_submission = reddit_operations.get_submission_by_url(result.url)
                except (APIException, praw.requests.exceptions.HTTPError, praw.requests.exceptions.ConnectionError):
                    log_this('ERROR: cant get submission by url, Invalid submission url!?')
                    targeted_submission = None
                debug(result.url)
                if targeted_submission:
                        already_watched = False
                        for thread in WatchedTreads.watched_threads_list:
                            if thread.thread_url in result.url:
                                already_watched = True
                        if not already_watched:
                            try:
                                reply = reddit_operations.comment_to_url(obj=targeted_submission,
                                                                         msg=result.msg_for_reply,
                                                                         result_url=result.url)
                                WatchedTreads(thread_url=result.url,
                                              srs_subreddit=str(result.args['dsubmission'].subreddit),
                                              srs_author=str(result.args['dsubmission'].author),
                                              bot_reply_object_id=reply.name,
                                              bot_reply_body=reply.body,
                                              poster_username=str(reply.author)
                                              )
                                #send_pm_to_owner("New Watch thread added by: {0} in: {1}".format(str(reply.author), result.url))
                            except AttributeError:
                                log_this("ERROR: ALL USERS BANNED IN: {}".format(targeted_submission.subreddit))
                        else:
                            debug("THREAD ALREADY WATCHED!")

            if result.msg_for_tweet:
                reddit_operations.tweet_this(result.msg_for_tweet)
                debug('New Topic Match in: {}'.format(result.args['dsubmission'].subreddit))


def log_this(logtext):
    with open('LOG.txt', 'a') as logfile:
        logfile.write('{0}: {1}\n'.format(time.ctime(), logtext))
    debug('Sent to LOG FILE: {}'.format(logtext))


def debug(debugtext, level=DEBUG_LEVEL, end='\n'):
    if level >= 1:
        print('* {}'.format(debugtext), end=end)


start_time = time.time()
botconfig = ConfigFiles()
username_bank = UsernameBank()
reddit_operations = RedditOperations()
reddit_operations.login(username_bank.defaut_username)
bot1 = ReddBot()


