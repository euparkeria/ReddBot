import time
import praw
import json
import os
import pickle
import re
from random import choice
from twython import Twython
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import sessionmaker

watched_subreddit = "+".join(['all'])
results_limit = 800
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


class SrsUser(Base):
    __tablename__ = 'SrsUsers'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True)
    subreddit = Column(String)
    reddit_id = Column(String, unique=True)
    last_check_date = Column(String)
    SRS_karma_balance = Column(Integer)
    invasion_number = Column(Integer)


class SocialMedia:
    def __init__(self):
        self.reddit_session = self.connect_to_reddit()
        self.twitter_session = self.connect_to_twitter()

    @staticmethod
    def connect_to_reddit():
        try:
            r = praw.Reddit(user_agent=bot_agent_name, api_request_delay=1)
            r.login(botconfig.bot_auth_info['REDDIT_BOT_USERNAME'], botconfig.bot_auth_info['REDDIT_BOT_PASSWORD'])
            debug('Logged in as {0}'.format(botconfig.bot_auth_info['REDDIT_BOT_USERNAME']))
        except:
            debug('ERROR: Cant login to Reddit.com')
        return r

    @staticmethod
    def connect_to_twitter():
        try:
            t = Twython(botconfig.bot_auth_info['APP_KEY'], botconfig.bot_auth_info['APP_SECRET'],
                        botconfig.bot_auth_info['OAUTH_TOKEN'], botconfig.bot_auth_info['OAUTH_TOKEN_SECRET'])
        except:
            debug('ERROR: Cant authenticate into twitter')
        return t


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
        except:
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
        except:
            debug("Error reading data file")
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


class WatchedTreads:
    watched_threads_list = []

    def __init__(self, thread_url, srs_subreddit, srs_author, bot_reply_object_id, bot_reply_body):
        self.thread_url = thread_url
        self.srs_subreddit = srs_subreddit
        self.srs_author = srs_author
        self.start_watch_time = time.time()
        self.already_processed_users = []
        self.bot_reply_object_id = bot_reply_object_id
        self.bot_reply_body = bot_reply_body
        self.keep_alive = 43200  # time to watch a thread in seconds

        WatchedTreads.watched_threads_list.append(self)
        self.savecache()
        debug('new watch object added')

    @staticmethod
    def savecache():
        try:
            with open(CACHEFILE, 'wb') as fa:
                pickle.dump(WatchedTreads.watched_threads_list, fa)
        except:
            debug('ERROR: Cant write cache file')

    @staticmethod
    def get_user_karma_balance(author, in_subreddit, user_comments_limit=200):
        user_srs_karma_balance = 0

        try:
            user = socmedia.reddit_session.get_redditor(author)
            for usercomment in user.get_overview(limit=user_comments_limit):
                if str(usercomment.subreddit) == in_subreddit:
                    user_srs_karma_balance += usercomment.score
        except:
            debug('ERROR: Cant get user SRS karma balance!!')
        return user_srs_karma_balance

    @staticmethod
    def get_authors_in_thread(thread):
        authors_list = []
        submission = socmedia.reddit_session.get_submission(thread)
        submission.replace_more_comments(limit=4, threshold=1)
        try:
            for comment in praw.helpers.flatten_tree(submission.comments):
                author = str(comment.author)
                if author not in botconfig.bot_auth_info['REDDIT_BOT_USERNAME']:
                    authors_list.append(author)
        except:
            debug('ERROR:couldnt get all authors from thread')
        return authors_list

    @staticmethod
    def edit_comment(comment_id, comment_body):
        try:
            comment = socmedia.reddit_session.get_info(thing_id=comment_id)
            comment.edit(comment_body)
            debug('Comment : {} edited.'.format(comment_id))
        except:
            debug('ERROR: Cant edit comment')

    @staticmethod
    def add_user_to_database(username, subreddit, srs_karma):
        session = DBSession()

        users_query = session.query(SrsUser).filter_by(username=username)
        if users_query.count() is False:
            stupiduser = SrsUser(username=username,
                                 subreddit=subreddit,
                                 last_check_date=time.time(),
                                 SRS_karma_balance=srs_karma)
            session.add(stupiduser)
            session.commit()

    @staticmethod
    def update():
        debug('Currently Watching {} threads.'.format(len(WatchedTreads.watched_threads_list)))

        karma_upper_limit = 3  # if poster has more than that amount of karma in the srs subreddit he is added

        for thread in WatchedTreads.watched_threads_list:
            srs_users = []
            debug('Now processing: {}'.format(thread.thread_url))

            for author in WatchedTreads.get_authors_in_thread(thread=thread.thread_url):
                if author not in thread.already_processed_users:
                    debug('--Checking user: {}'.format(author), end=" ")
                    user_srs_karma_balance = WatchedTreads.get_user_karma_balance(author=author,
                                                                                  in_subreddit=thread.srs_subreddit)
                    debug(',/r/{0} karma score:{1} '.format(thread.srs_subreddit, user_srs_karma_balance), end=" ")
                    if user_srs_karma_balance >= karma_upper_limit:
                        srs_users.append(author)
                        WatchedTreads.add_user_to_database(username=author,
                                                           subreddit=thread.srs_subreddit,
                                                           srs_karma=user_srs_karma_balance)
                        debug('MATCH', end=" ")
                    debug('.')
                    thread.already_processed_users.append(author)

            if srs_users:
                WatchedTreads.append_lines_to_comment(thread=thread, srs_users=srs_users)

            WatchedTreads.check_if_expired(thread)

        WatchedTreads.savecache()

    @staticmethod
    def append_lines_to_comment(thread, srs_users):
        split_mark = '\n\n-----\n'
        splitted_comment = thread.bot_reply_body.split(split_mark, 1)
        srs_users_lines = ''.join(['\n\n* [/u/' + user + '](http://np.reddit.com/u/' + user + ')'for user in srs_users])
        thread.bot_reply_body = splitted_comment[0] + srs_users_lines + split_mark + splitted_comment[1]
        WatchedTreads.edit_comment(comment_id=thread.bot_reply_object_id, comment_body=thread.bot_reply_body)


    @staticmethod
    def check_if_expired(thread):
            time_watched = time.time() - thread.start_watch_time
            debug('--Watched for {} hours'.format(time_watched/60/60))
            if time_watched > thread.keep_alive:  # if older than 8 hours
                WatchedTreads.watched_threads_list.remove(thread)
                debug('--Watched Thread Removed!')


class MatchedSubmissions:

    matching_results = []

    def __init__(self, dsubmission, target, keyword_lists):
        self.args = {'dsubmission': dsubmission, 'target': target, 'keyword_lists': keyword_lists}
        self.body_text = self._get_body_text()
        self.url = self._get_clean_url()

        self.is_srs = False
        self.keyword_matched = False

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
        if self.is_srs:
            quote = QuoteBank()
            quote = quote.get_quote(self.args['keyword_lists']['quotes'], self.args['dsubmission'].title)
            submissionlink = make_np(self.args['dsubmission'].permalink)
            brigade_subreddit_link = '*[/r/{0}]({1})*'.format(self.args['dsubmission'].subreddit, submissionlink)

            self.msg_for_reply = "#**NOTICE**:\nThis thread is the target of a *possible* downvote brigade from " \
                                 "{2}^submission ^linked\n\n" \
                "**Submission Title:**\n\n* *{1}*\n\n**Members of {2}" \
                " involved in this thread:**" \
                "^list ^updated ^every ^5 ^minutes ^for ^12 ^hours\n\n \n\n-----\n ^★ *{0}* ^★\n\n " \
                "[^|bot ^twitter ^feed|](https://twitter.com/bot_redd)"\
                .format(quote,
                self.args['dsubmission'].title,
                brigade_subreddit_link)
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

        loop_counter = 0
        while True:
            loop_counter += 1
            if loop_counter >= secondary_timer / loop_timer:
                self._maintenance_loop()
                loop_counter = 0

            self._mainlooper()

    def _maintenance_loop(self):
        debug('Maintenance loop')
        maint_timer = time.time()
        avg_subs_per_sec = self.permcounters['submissions'] / (time.time() - start_time)
        debug('avg_subs_per_sec {}'.format(avg_subs_per_sec))
        #try:
        for function in self._maintenance_functions():
            function()
        #except:
            #self.debug('Maintenance Loop Error')
        maint_timer = time.time() - maint_timer
        debug('maint_seconds {}'.format(maint_timer))

        increase_pulllimit_by = int((maint_timer * avg_subs_per_sec) + 1)
        self.pulllimit['submissions'] += increase_pulllimit_by
        debug('Pulllimit increased by:{}'.format(increase_pulllimit_by))

    @staticmethod
    def _maintenance_functions():
        def watchthreads():
            WatchedTreads.update()

        def reloadconfig():
            botconfig.check_for_updated_config()

        return [watchthreads, reloadconfig]

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

    @staticmethod
    def get_comments_or_subs(placeholder_id='', subreddit=watched_subreddit,
                             limit=results_limit, target='submissions'):
        if target == 'submissions':
            return socmedia.reddit_session.get_subreddit(subreddit).get_new(limit=limit,
                                                                            place_holder=placeholder_id)
        if target == 'comments':
            return socmedia.reddit_session.get_comments(subreddit, limit=limit)

    def _get_new_comments_or_subs(self, target):

        results = ReddBot.get_comments_or_subs(placeholder_id=self.placeholder_id, subreddit=watched_subreddit,
                                               limit=self.pulllimit[target], target=target)

        new_submissions_list = []
        try:
            for submission in results:
                if submission.id not in self.processed_objects[target]:
                    new_submissions_list.append(submission)
                    self.processed_objects[target].append(submission.id)  # add to list of already processed submission
                    self.cont_num[target] += 1   # count the number of submissions processed each run
            if new_submissions_list:
                self.placeholder_id = new_submissions_list[0].id
        except:
            debug('ERROR:Cannot connect to reddit!!!')
        return new_submissions_list

    def _contentloop(self, target):
        new_submissions = self._get_new_comments_or_subs(target)

        if new_submissions:

            for new_submission in new_submissions:
                MatchedSubmissions(target=target, dsubmission=new_submission, keyword_lists=botconfig.redd_data)

            if MatchedSubmissions.matching_results:
                self.dispatch_nitifications(results_list=MatchedSubmissions.matching_results)
                MatchedSubmissions.purge_list()

    @staticmethod
    def commenter(obj, msg):
        if len(obj.comments) > 1:
            debug('ADD to ID:{0}'.format(obj.comments[0].id))
            return obj.add_comment(msg)
        else:
            debug('REPLY to ID:{0}'.format(obj.comments[0].id))
            return obj.comments[0].reply(msg)

    def dispatch_nitifications(self, results_list):
        for result in results_list:
            if result.msg_for_reply:
                try:
                    targeted_submission = socmedia.reddit_session.get_submission(result.url)
                except:
                    debug('ERROR: cant get submission by url, Invalid submission url!?')
                    targeted_submission = None
                debug(result.url)
                if targeted_submission:
                    try:
                        reply = self.commenter(obj=targeted_submission, msg=result.msg_for_reply)
                        WatchedTreads(thread_url=result.url,
                                      srs_subreddit=str(result.args['dsubmission'].subreddit),
                                      srs_author=str(result.args['dsubmission'].author),
                                      bot_reply_object_id=reply.name,
                                      bot_reply_body=reply.body)

                        debug('AntiBrigadeBot NOTICE sent')
                    except:
                        log_this('Bot is BANNED in:{}, cant reply ):'.format(targeted_submission.subreddit))

            if result.msg_for_tweet:
                tweet_this(result.msg_for_tweet)
                debug('New Topic Match in: {}'.format(result.args['dsubmission'].subreddit))


def send_pm_to_owner(pm_text):
    try:
        socmedia.reddit_session.send_message(botconfig.bot_auth_info['REDDIT_PM_TO'], pm_text)
    except:
        debug('ERROR:Cant send pm')


def make_np(link):
    return link.replace('http://www.reddit.com', 'http://np.reddit.com')


def tweet_this(msg):
    if len(msg) > 140:
        msg = msg[:139]
        debug('MSG exceeding 140 characters!!')
    try:
        socmedia.twitter_session.update_status(status=msg)
        debug('TWEET SENT!!!')
    except:
        debug('ERROR: couldnt update twitter status')


def log_this(logtext):
    with open('LOG.txt', 'a') as logfile:
        logfile.write('{0}: {1}\n'.format(time.ctime(), logtext))
    debug('LOOGGED {}'.format(logtext))


def debug(debugtext, level=DEBUG_LEVEL, end='\n'):
    if level >= 1:
        print('* {}'.format(debugtext), end=end)


start_time = time.time()
botconfig = ConfigFiles()
socmedia = SocialMedia()

bot1 = ReddBot()
