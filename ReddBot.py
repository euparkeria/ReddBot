import threading
import time
import math
import praw
import json
import pickle
import re
from random import choice
from praw.errors import HTTPException, APIException, ClientException, InvalidCaptcha
from requests import exceptions
from twython import Twython
from twython import TwythonError

import BotDatabase
import BotLogging

watched_subreddit = "+".join(['all'])
results_limit = 2000
results_limit_comm = 900
karma_balance_post_limit = 500
bot_agent_name = 'LeninBot v2'
loop_timer = 60
secondary_timer = loop_timer * 5

CACHEFILE = 'reddbot.cache'
AUTHFILE = 'ReddAUTH.json'
DATACACHE = 'DataCACHE.json'


class UsernameBank:
    def __init__(self):
        self.current_username = ""  # currently logged on with username
        self.username_count = len(botconfig.bot_auth_info['REDDIT_BOT_USERNAME'])
        self.already_tried = []
        self.defaut_username = botconfig.bot_auth_info['REDDIT_BOT_USERNAME'][0]  # first username is default

    def get_username(self, exclude=''):
        """without arguments it will exclude the current username and login with random one"""
        if not exclude:
            exclude = self.current_username
        self.already_tried.append(exclude)

        new_random_username = [x for x in botconfig.bot_auth_info['REDDIT_BOT_USERNAME']
                               if x not in self.already_tried]
        if new_random_username:
            new_name = choice(new_random_username)
            self.already_tried.append(new_name)
            return new_name
        else:
            return self.defaut_username

    def purge_tried_list(self):
        self.already_tried = []


class MaintThread(threading.Thread):
    """Separate thread for the Maintanance functions"""

    def __init__(self, threadid, name):
        threading.Thread.__init__(self)
        self.threadID = threadid
        self.name = name

    def run(self):
        BotLogging.BotLogger.info("Starting " + self.name)
        '''Maintanence functions bellow'''
        botconfig.check_for_updated_config()
        WatchedTreads.update_all()


class SocialMedia:
    """handles reddit and twiter API init and sessions"""
    def __init__(self):
        self.reddit_session = self.connect_to_reddit()
        self.twitter_session = self.connect_to_twitter()
        #self.imgur_client = self.connect_to_imgur()

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
            BotLogging.BotLogger.error('Cant authenticate into twitter')
        return t
'''
    @staticmethod
    def connect_to_imgur():
        imgur_client = ImgurClient(botconfig.bot_auth_info['IMGUR_CLIENT_ID'],
                                   botconfig.bot_auth_info['IMGUR_CLIENT_SECRET'])
        return imgur_client
'''


class ConfigFiles:
    def __init__(self):
        self.data_modified_time = 0
        self.cache = self.loadcache()

        self.redd_data = None
        self.bot_auth_info = None
        self.check_for_updated_config()

    def check_for_updated_config(self):
        self.redd_data = self.readdatafile()
        self.bot_auth_info = self.readauthfile()
        BotLogging.BotLogger.info('CONFIG FILES RELOADED!')

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
            BotLogging.BotLogger.info('Cache File not Pressent')
            return []

    def readdatafile(self):

        redd_data = BotDatabase.get_from_db()
        if redd_data:
            with open(DATACACHE, 'w') as outfile:
                json.dump(redd_data, outfile)


        redd_data['KEYWORDS'] = sorted(redd_data['KEYWORDS'], key=len, reverse=True)
        redd_data['SRSs'] = [x.lower() for x in redd_data['SRSs']]
        # redd_data['quotes'] = [''.join(('^', x.replace(" ", " ^"))) for x in redd_data['quotes']]

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
        # return punct_clear.split()
        return punct_clear

    def get_quote(self, quotes, topicname):
        topicname = self.remove_punctuation(topicname.lower())
        for quote in quotes:
            match = self.lcs(topicname, self.remove_punctuation(quote.lower()))
            # TODO: look for more than one match per quote

            if match:
                match_word_list = match.split()
                if match_word_list and len(max(match_word_list, key=len)) >= 6:  # if there is a word of at least 6 characters

                    for keyword in botconfig.redd_data['KEYWORDS']:
                        if self.lcs(keyword.lower(), match.lower()) in botconfig.redd_data['KEYWORDS']:
                            self.quotes_matched[match + "-KEYWORD{:.>5}".format(quotes.index(quote))] = quote
                            self.keyword_matched = True
                    if not self.keyword_matched:
                        self.quotes_matched[match + "{:.>5}".format(quotes.index(quote))] = quote

        if self.quotes_matched:
            keys = list(self.quotes_matched.keys())

            if self.keyword_matched:
                keyword_matches_keys = [key for key in keys if '-KEYWORD' in key]
                BotLogging.BotLogger.info(keyword_matches_keys)
                quote_to_return = self.quotes_matched[choice(keyword_matches_keys)]
            else:
                longest_keys = [key for key in keys if len(key) >= len(max(keys, key=len)) - 2]  # all longest
                BotLogging.BotLogger.info(longest_keys)
                quote_to_return = self.quotes_matched[choice(longest_keys)]

        else:
            quote_to_return = choice(quotes)

        session = BotDatabase.Session()

        quote_query = session.query(BotDatabase.BotQuotes).filter_by(quote=quote_to_return).first()
        BotLogging.BotLogger.info(quote_to_return)
        BotLogging.BotLogger.info(quote_query)
        if quote_query:
            if quote_query.usedcount:
                quote_query.usedcount += 1
            else:
                quote_query.usedcount = 1

        return ''.join(('^', quote_to_return.replace(" ", " ^")))


class RedditOperations:
    """Contains reddit, twitter and imgur api related operations"""

    def __init__(self):
        """class SocialMedia should only be needed within this class so init here"""
        self.socmedia = SocialMedia()

    def login(self, username=''):
        try:
            if not username:
                username = username_bank.get_username()
            self.socmedia.reddit_session.login(username, botconfig.bot_auth_info['REDDIT_BOT_PASSWORD'])
            username_bank.current_username = username
            BotLogging.BotLogger.info('Sucessfully logged in as {0}'.format(username_bank.current_username))
            time.sleep(3)
        except praw.errors.APIException:
            BotLogging.BotLogger.error('Cant login to Reddit.com')

    def get_post_attribute(self, url, attribute):
        """returns a post attribute as a string
        :param url: url of the post
        :param attribute: attribute to get
        """
        value = None
        try:
            post_object = self.get_post_object(url)
            value = getattr(post_object, attribute)

        except (AttributeError,
                APIException,
                ClientException,
                HTTPException):
            BotLogging.BotLogger.error("Couldnt get post score")
        return str(value)

    def get_post_object(self, url):
        """
        returns correct object type for reply depending on url, comment or submission
        :param url:
        """
        post_object = self.get_submission_by_url(url=url)
        comment_url_pattern = re.compile("http[s]?://[a-z]{0,3}\.?[a-z]{0,2}\.?reddit\.com/r/.{1,20}/comments/.{6,8}/.*/.{6,8}")

        if comment_url_pattern.match(url):
            return post_object.comments[0]
        else:
            return post_object

    def get_user_karma_balance(self, author, in_subreddit, user_comments_limit=karma_balance_post_limit):
        """
        :param author:
        :param in_subreddit:
        :param user_comments_limit:
        :return:
        """
        user_srs_karma_balance = 0

        try:
            user = self.socmedia.reddit_session.get_redditor(author)
            for usercomment in user.get_overview(limit=user_comments_limit):
                if str(usercomment.subreddit) == in_subreddit:
                    user_srs_karma_balance += usercomment.score
        except (APIException,
                ClientException,
                praw.errors.NotFound):
            BotLogging.BotLogger.error('Cant get user SRS karma balance!!')
        return user_srs_karma_balance

    def get_authors_in_thread(self, url):
        """
        returns list of usernames writting in a thread by url
        :param url:
        :return:
        """
        authors_list = []
        try:
            submission = self.get_submission_by_url(url)
            submission.replace_more_comments(limit=None, threshold=1)
            for comment in praw.helpers.flatten_tree(submission.comments):
                author = str(comment.author)
                if author not in botconfig.bot_auth_info['REDDIT_BOT_USERNAME']:
                    authors_list.append(author)
        except (APIException,
                HTTPException):
            BotLogging.BotLogger.error('couldnt get all authors from thread')
        return authors_list

    def edit_comment(self, comment_id, comment_body, poster_username):
        """
        :param comment_id:
        :param comment_body:
        :param poster_username:
        :return:
        """
        if username_bank.current_username != poster_username:
            self.login(username=poster_username)
        try:
            comment = self.socmedia.reddit_session.get_info(thing_id=comment_id)
            comment.edit(comment_body)
            BotLogging.BotLogger.info('Comment : {} edited.'.format(comment_id))
            if username_bank.current_username != username_bank.defaut_username:
                self.login(username_bank.defaut_username)
        except (APIException,
                HTTPException):
            BotLogging.BotLogger.error('Cant edit comment')

    def get_comments_or_subs(self, placeholder_id='', subreddit=watched_subreddit,
                             limit=results_limit, target='submissions'):
        if target == 'submissions':
            return self.socmedia.reddit_session.get_subreddit(subreddit).get_new(limit=limit,
                                                                                 place_holder=placeholder_id)
        if target == 'comments':
            return self.socmedia.reddit_session.get_comments(subreddit, limit=limit)

    def reply_to_url(self, msg, result_url):
        """
        reply to comment or add a comment to submission
        :param msg:
        :param result_url:
        :return:
        """

        '''get correct object depending on url'''
        return_obj = None
        post_object = reddit_operations.get_post_object(result_url)

        retry_attemts = username_bank.username_count

        for retry in range(retry_attemts):
            try:
                if isinstance(post_object, praw.objects.Comment):
                    return_obj = post_object.reply(msg)
                    BotLogging.BotLogger.info('NOTICE REPLIED to ID:{0}'.format(post_object.id))
                    break
                elif isinstance(post_object, praw.objects.Submission):
                    return_obj = post_object.add_comment(msg)
                    BotLogging.BotLogger.info('NOTICE ADDED to ID:{0}'.format(post_object.id))
                    break
            except (APIException,
                    HTTPException):
                BotLogging.BotLogger.error('{1} is BANNED in:{0}, reloging'.format(post_object.subreddit, username_bank.current_username))
                self.login()

        if username_bank.current_username != username_bank.defaut_username:
            self.login(username_bank.defaut_username)
        username_bank.purge_tried_list()
        return return_obj

    def get_submission_by_url(self, url):
        """
        :param url:
        :return:
        """

        url = url.replace("www.np.", "np.") # in case someone types www.np which does not match the ssl cert
        return self.socmedia.reddit_session.get_submission(url)

    def send_pm_to_owner(self, pm_text):
        """
        :param pm_text:
        :return:
        """
        try:
            self.socmedia.reddit_session.user.send_message(botconfig.bot_auth_info['REDDIT_PM_TO'], pm_text)
        except (APIException, HTTPException):
            BotLogging.BotLogger.error('Cant send pm')

    @staticmethod
    def make_np(link):
        return link.replace('www.reddit.com', 'np.reddit.com')

    def check_if_user_exists(self, username):
        """
        check if user exists or shadowbanned
        :param username:
        :return:
        """
        user = None
        try:
            user = self.socmedia.reddit_session.get_redditor(username)
        except HTTPException as e:
            if e.message.status_code == 404:
                return False
        except (APIException,
                HTTPException):
            BotLogging.BotLogger.error('Error checking if user exists')
        if user:
            return True
        return False

    def tweet_this(self, msg):
        if len(msg) > 140:
            msg = msg[:139]
            BotLogging.BotLogger.error('MSG exceeding 140 characters!!')
        try:
            self.socmedia.twitter_session.update_status(status=msg)
            BotLogging.BotLogger.info('TWEET SENT!!!')
        except TwythonError:
            BotLogging.BotLogger.error('couldnt update twitter status')


class WatchedTreads:

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


    @staticmethod
    def savecache():
        try:
            with open(CACHEFILE, 'wb') as fa:
                pickle.dump(bot1.Watched_Threads, fa)
        except IOError:
            BotLogging.BotLogger.error('Cant write cache file')

    @staticmethod
    def update_user_database(username, subreddit, srs_karma):
        """
        :param username:
        :param subreddit:
        :param srs_karma:
        :return:
        """
        session = BotDatabase.Session()
        users_query = WatchedTreads.query_user_database(username, subreddit, session=session)
        invasion_number = 0

        if users_query:
            if users_query.invasion_number:
                users_query.invasion_number += 1
                invasion_number = users_query.invasion_number
            else:
                users_query.invasion_number = 1
            users_query.last_check_date = time.time()
            users_query.SRS_karma_balance = srs_karma
            BotLogging.BotLogger.info("Updating database entry on: {1}@{0} !".format(subreddit, username))
        else:
            BotLogging.BotLogger.info("{1}@{0} NOT IN database!".format(subreddit, username))
            stupiduser = BotDatabase.SrsUser(username=username,
                                             subreddit=subreddit,
                                             last_check_date=time.time(),
                                             srs_karma_balance=srs_karma)
            session.add(stupiduser)

        session.commit()
        BotDatabase.Session.remove()
        BotLogging.BotLogger.info('Database Updated')
        return invasion_number

    @staticmethod
    def query_user_database(username, subreddit, session=None):
        """Will return False if user doesnt exist, if no session is give as argument will open and close it's own"""
        no_session_argument = False
        if not session:
            session = BotDatabase.Session()
            no_session_argument = True
        users_query = session.query(BotDatabase.SrsUser).filter_by(username=username, subreddit=subreddit).first()
        if no_session_argument:
            BotDatabase.Session.remove()
        if users_query:
            return users_query
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
            #bot_comment_changed = True

        if bot_comment_changed:
            reddit_operations.edit_comment(comment_id=self.bot_reply_object_id,
                                           comment_body=self.bot_body,
                                           poster_username=self.poster_username)

        if self.check_if_expired():
            BotLogging.BotLogger.info('This Thread has Expired and is Removed! {0} '.format(self.thread_url))

    def check_for_new_invaders(self):
        karma_upper_limit = 5  # if poster has more than that amount of karma in the srs subreddit he is added
        srs_users = []
        new_user_counter = 0

        for author in reddit_operations.get_authors_in_thread(url=self.thread_url):
            if author not in self.already_processed_users:
                new_user_counter += 1
                user_srs_karma_balance = reddit_operations.get_user_karma_balance(author=author,
                                                                                  in_subreddit=self.srs_subreddit)

                if user_srs_karma_balance >= karma_upper_limit:
                    srs_users.append({'username': author, 'tag': '', 'karma': user_srs_karma_balance})
                    invasion_number = WatchedTreads.update_user_database(username=author,
                                                                         subreddit=self.srs_subreddit,
                                                                         srs_karma=user_srs_karma_balance)
                    if invasion_number:
                        srs_users[-1]['tag'] = int(round((math.log(invasion_number, 1.902) - 1.5))) * '☠'

                self.already_processed_users.append(author)
        BotLogging.BotLogger.info('Processed {0} new users for thread: {1} User LIST:'.format(new_user_counter, self.thread_url))
        BotLogging.BotLogger.info([user['username'] + ':' + str(user['karma']) for user in srs_users])
        return srs_users

    def update_graph(self):
        pass

    @staticmethod
    def update_all():
        BotLogging.BotLogger.info('Currently Watching {} threads.'.format(len(bot1.Watched_Threads)))
        for thread in bot1.Watched_Threads:
            thread.update()
        WatchedTreads.savecache()

    def add_user_lines(self, srs_users):
        split_mark = '\n\n-----\n'
        splitted_comment = self.bot_body.split(split_mark, 1)
        srs_users_lines = ''.join(['\n\n* [/u/'
                                   + user['username']
                                   + '](https://np.reddit.com/u/'
                                   + user['username']
                                   + ') '
                                   + user['tag']
                                   + '\n\n' for user in srs_users])
        return splitted_comment[0] + srs_users_lines + split_mark + splitted_comment[1]

    def check_if_expired(self):
            time_watched = time.time() - self.start_watch_time
            BotLogging.BotLogger.info('{0} Watched for {1} hours'.format(self.thread_url, time_watched/60/60))
            if time_watched > self.keep_alive:  # if older than 8 hours
                bot1.Watched_Threads.remove(self)
                return True


class MatchedSubmissions:

    matching_results = []

    def __init__(self, dsubmission, target):
        self.args = {'dsubmission': dsubmission, 'target': target}
        self.body_text = self._get_body_text()
        self.url = self._get_clean_url()
        self.subreddit = str(self.args['dsubmission'].subreddit).lower()

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
        for keyword in botconfig.redd_data['KEYWORDS']:
            if keyword.lower() in self.body_text.lower():
                self.keyword_matched = keyword
                return True
        return False

    def _detect_brigade(self):

        reddit_link_pattern = re.compile("http[s]?://[a-z]{0,3}\.?[a-z]{0,2}\.?reddit\.com/r/.{1,20}/comments/.*")

        if self.subreddit in botconfig.redd_data['SRSs']:
            if reddit_link_pattern.match(self.url) and not self.args['dsubmission'].is_self:
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
            quote = quote.get_quote(botconfig.redd_data['quotes'], self.args['dsubmission'].title)
            submissionlink = reddit_operations.make_np(self.args['dsubmission'].permalink)
            brigade_subreddit_link = '*[/r/{0}]({1})*'.format(self.args['dsubmission'].subreddit, submissionlink)

            members_active = ['Members of {0} participating in this thread:'.format(brigade_subreddit_link)]

            stars = ['★']

            explanations = ['This thread has been targeted by a *possible* downvote-brigade from **{0}**'
                            .format(brigade_subreddit_link),
                            'The above post was just linked from **{0}** in a *possible* attempt to downvote it.'
                            .format(brigade_subreddit_link)
                            ]

            lines = ['{0}\n\n'.format(choice(explanations)),
                     '* *[{0}]({1})*\n\n'.format(self.args['dsubmission'].title, submissionlink),
                     '**{0}**\n\n'.format(choice(members_active)),
                     '\n\n'
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
        self.mthread = None  # maintanence thead
        self.Watched_Threads = botconfig.cache   # list of currently watched brigade threads

    def start_bot(self):
        loop_counter = 0
        while True:
            loop_counter += 1
            if loop_counter >= secondary_timer / loop_timer or self.first_run:
                self._maintenance_loop()
                loop_counter = 0

            self._mainlooper()
            time.sleep(loop_timer)

    def _maintenance_loop(self):
        maint_thread_name = "Maintenance Thread"
        if self.first_run:
            self.mthread = MaintThread(1, maint_thread_name)

        if not self.mthread.isAlive():
                self.mthread = MaintThread(1, maint_thread_name)
                self.mthread.start()

    def _mainlooper(self):

        self.cont_num['submissions'], self.cont_num['comments'] = 0, 0

        for loop in self.loops:
            self._contentloop(target=loop)
            buffer_reset_lenght = self.pulllimit[loop] * 10
            if len(self.processed_objects[loop]) >= buffer_reset_lenght:
                self.processed_objects[loop] = self.processed_objects[loop][int(len(self.processed_objects[loop]) / 2):]
                # BotLogging.BotLogger.debug('Buffers LENGHT after trim {0}'.format(len(self.processed_objects[loop])))
            if not self.first_run:
                self.pulllimit[loop] = self._calculate_pull_limit(self.cont_num[loop], target=loop)
            self.permcounters[loop] += self.cont_num[loop]

        BotLogging.BotLogger.info('Sub:{0}, this run:{1}.'
              'Comments:{2}, this run:{3}'
              .format(self.permcounters['submissions'],
                      self.cont_num['submissions'], self.permcounters['comments'],
                      self.cont_num['comments']))

        self.first_run = False

        BotLogging.BotLogger.debug(self.pulllimit['submissions'])
        BotLogging.BotLogger.debug(self.pulllimit['comments'])

    def _calculate_pull_limit(self, lastpullnum, target):
        """this needs to be done better"""
        add_more = {'submissions': 70, 'comments': 300}   # how many items above last pull number to pull next run

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
            BotLogging.BotLogger.error('Cannot connect to reddit!!!')
        return new_submissions_list

    def _contentloop(self, target):
        new_submissions = self._get_new_comments_or_subs(target)

        if new_submissions:

            for new_submission in new_submissions:
                MatchedSubmissions(target=target, dsubmission=new_submission)

            if MatchedSubmissions.matching_results:
                self.dispatch_nitifications(results_list=MatchedSubmissions.matching_results)
                MatchedSubmissions.purge_list()

    def dispatch_nitifications(self, results_list):
        for result in results_list:
            if result.msg_for_reply:
                try:
                    targeted_submission = reddit_operations.get_submission_by_url(result.url)
                except (APIException, HTTPException):
                    BotLogging.BotLogger.error('cant get submission by url, Invalid submission url!?')
                    targeted_submission = None
                BotLogging.BotLogger.debug(result.url)
                if targeted_submission:
                        already_watched = False
                        for thread in self.Watched_Threads:

                            if thread.thread_url in result.url:
                                already_watched = True
                        if not already_watched:
                            try:
                                reply = reddit_operations.reply_to_url(msg=result.msg_for_reply,
                                                                       result_url=result.url)
                                thread = WatchedTreads(thread_url=result.url,
                                                       srs_subreddit=str(result.args['dsubmission'].subreddit),
                                                       srs_author=str(result.args['dsubmission'].author),
                                                       bot_reply_object_id=reply.name,
                                                       bot_reply_body=reply.body,
                                                       poster_username=str(reply.author)
                                                       )
                                self.Watched_Threads.append(thread)
                                WatchedTreads.savecache()
                                #send_pm_to_owner("New Watch thread added by: {0} in: {1}".format(str(reply.author), result.url))
                            except AttributeError:
                                BotLogging.BotLogger.error("ALL USERS BANNED IN: {}".format(targeted_submission.subreddit))
                        else:
                            BotLogging.BotLogger.info("THREAD ALREADY WATCHED!")

            if result.msg_for_tweet:
                reddit_operations.tweet_this(result.msg_for_tweet)
                BotLogging.BotLogger.info('New Topic Match in: {}'.format(result.args['dsubmission'].subreddit))


start_time = time.time()
botconfig = ConfigFiles()
username_bank = UsernameBank()
reddit_operations = RedditOperations()

reddit_operations.login(username_bank.defaut_username)

bot1 = ReddBot()
bot1.start_bot()
