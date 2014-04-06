__author__ = 'mekoneko'

import time
import praw
import json
import os
from random import choice
from twython import Twython

watched_subreddit = 'all'
results_limit = 500
results_limit_comm = 900
bot_agent_name = 'ReddBot v0.8 /u/AntiBrigadeBot'
loop_timer = 60
secondary_timer = loop_timer * 10
DEBUG_LEVEL = 1


class ConnectSocialMedia:

    def __init__(self, authinfo, useragent):

        self.reddit_session = self.connect_to_reddit(authinfo, useragent=useragent)
        self.twitter_session = self.connect_to_twitter(authinfo)

    @staticmethod
    def connect_to_reddit(authinfo, useragent):
        try:
            r = praw.Reddit(user_agent=useragent, api_request_delay=1)
            r.login(authinfo['REDDIT_BOT_USERNAME'], authinfo['REDDIT_BOT_PASSWORD'])
        except:
            print('ERROR: Cant login to Reddit.com')
        return r

    @staticmethod
    def connect_to_twitter(authinfo):
        try:
            t = Twython(authinfo['APP_KEY'], authinfo['APP_SECRET'],
                        authinfo['OAUTH_TOKEN'], authinfo['OAUTH_TOKEN_SECRET'])
        except:
            print('ERROR: Cant authenticate into twitter')
        return t


class ReadConfigFiles:
    def __init__(self):
        self.data_modified_time = 0

    @staticmethod
    def readauthfile(authfilename):
        with open(authfilename, 'r', encoding='utf-8') as f:
            bot_auth_info = json.load(f)
        return bot_auth_info

    def readdatafile(self, datafilename):
        try:
            self.data_modified_time = os.stat(datafilename).st_mtime
            with open(datafilename, 'r', encoding='utf-8') as f:
                redd_data = json.load(f)
                redd_data['KEYWORDS'] = sorted(redd_data['KEYWORDS'], key=len, reverse=True)
                redd_data['SRSs'] = [x.lower() for x in redd_data['SRSs']]
                #redd_data['quotes'] = [''.join(('^', x.replace(" ", " ^"))) for x in redd_data['quotes']]
        except:
            print("Error reading data file")
        return redd_data


class MatchedSubmissions:

    matching_results = []

    def __init__(self, dsubmission, target, keyword_lists):
        self.args = {'dsubmission': dsubmission, 'target': target, 'keyword_lists': keyword_lists}
        self.is_srs = False
        self.keyword_matched = False
        self.body_text = self._get_body_text()
        self.msg_for_tweet = None
        self.msg_for_reply = None

        # list of checks on each submissions, functions MUST return True or False
        self.checks = [self._find_matching_keywords(),
                       self._detect_brigade()]
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

    def _get_body_text(self):
        if self.args['target'] == 'submissions':
            return self.args['dsubmission'].title + self.args['dsubmission'].selftext
        if self.args['target'] == 'comments':
            return self.args['dsubmission']

    def _find_matching_keywords(self):
        for keyword in self.args['keyword_lists']['KEYWORDS']:
            if keyword.lower() in self.body_text.lower():
                self.keyword_matched = keyword
                return True
        return False

    def _detect_brigade(self):
        subreddit = str(self.args['dsubmission'].subreddit)
        if subreddit.lower() in self.args['keyword_lists']['SRSs'] and 'reddit.com' in self.args['dsubmission'].url \
                and not self.args['dsubmission'].is_self:
            self.is_srs = True
            return True
        return False

    @staticmethod
    def purge_list():
        MatchedSubmissions.matching_results = []

    def _find_good_quote(self, quotes, topicname):
        quotes_matched = {}

        def remove_punctuation(quote):
            punctuation = "!\"#$%&'()*+,-.:;<=>?@[\\]^_`{|}~"
            punct_clear = ""
            for letter in quote:
                if letter not in punctuation:
                    punct_clear += letter
            return punct_clear.split()
            #return s_sans_punct

        def longest_common_substring(s1, s2):
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

        topicname = remove_punctuation(topicname.lower())
        for i in range(len(quotes)):
            q = remove_punctuation(quotes[i].lower())

            match = ' '.join(longest_common_substring(topicname, q))
            #match = longest_common_substring(topicname, q)
            if len(match):
                quotes_matched[match + "{:.>4}".format(i)] = quotes[i]

        if quotes_matched:
            keys = list(quotes_matched.keys())
            longest_keys = []
            for key in keys:
                if len(key) == len(max(keys, key=len)):
                    longest_keys.append(key)
            print(longest_keys)
            quote_to_return = quotes_matched[choice(longest_keys)]

        else:
            quote_to_return = choice(quotes)
        return ''.join(('^', quote_to_return.replace(" ", " ^")))

    def _brigade_message(self):
        if self.is_srs:
            quote = self._find_good_quote(self.args['keyword_lists']['quotes'], self.args['dsubmission'].title)
            self.msg_for_reply = "#**NOTICE**:\nThis comment is the target of a possible downvote brigade from " \
                                 "[/r/{0}]({1})^linked\n\n" \
                "**Title:**\n\n* *{3}* \n\n---\n ^★ *{2}* ^★".format(self.args['dsubmission'].subreddit,
                                                                     self.args['dsubmission'].permalink,
                                                                     quote,
                                                                     self.args['dsubmission'].title)
            return True
        return False

    def _keyword_match_tweet(self):
        if self.keyword_matched and not self.is_srs:
            self.msg_for_tweet = 'Submission regarding #{0} posted in /r/{1} : {2} #reddit'.format(
                self.keyword_matched, self.args['dsubmission'].subreddit, self.link)
            return True
        return False

    def _brigade_tweet(self):
        if self.is_srs and self.keyword_matched:
            self.msg_for_tweet = 'ATTENTION: possible reactionary brigade from /r/{1} regarding #{0}: {2} #reddit'\
                .format(self.keyword_matched, self.args['dsubmission'].subreddit, self.link)

            return True
        return False


class ReddBot:

    def __init__(self, useragent, authfilename, datafilename):
        self.first_run = True
        self.args = {'useragent': useragent, 'authfilename': authfilename, 'datafilename': datafilename}
        self.pulllimit = {'submissions': results_limit, 'comments': results_limit_comm}
        self.cont_num = {'comments': 0, 'submissions': 0}
        self.processed_objects = {'comments': [], 'submissions': []}
        self.loops = ['submissions']  # 'submissions' and 'comments' loops
        self.permcounters = {'comments': 0, 'submissions': 0}
        self.loop_counter = 0
        self.redd_data = {}
        self.bot_auth_info = {}
        self.reddit_session = None
        self.twitter = None
        self.config = ReadConfigFiles()

        self.placeholder_id = None  # this doesn't always work !? but it will lower the traffic to some extend

        while True:
            self.loop_counter += 1
            if self.loop_counter >= secondary_timer / loop_timer:
                self.debug('Maintenance loop')
                self.loop_counter = 0
            self._mainlooper()

    def _mainlooper(self):

        if os.stat(self.args['datafilename']).st_mtime > self.config.data_modified_time:
            self.redd_data = self.config.readdatafile(self.args['datafilename'])
            self.bot_auth_info = self.config.readauthfile(self.args['authfilename'])
            self.debug('CONFIG FILES REREAD!')
            bot_session = ConnectSocialMedia(self.bot_auth_info, useragent=self.args['useragent'])
            self.reddit_session = bot_session.reddit_session
            self.twitter = bot_session.twitter_session
            self.debug('RECONNECTED!')

        self.cont_num['submissions'], self.cont_num['comments'] = 0, 0

        for loop in self.loops:
            self._contentloop(target=loop)
            buffer_reset_lenght = self.pulllimit[loop] * 10
            if len(self.processed_objects[loop]) >= buffer_reset_lenght:
                self.processed_objects[loop] = self.processed_objects[loop][int(len(self.processed_objects[loop]) / 2):]
                self.debug('Buffers LENGHT after trim {0}'.format(len(self.processed_objects[loop])))
            if not self.first_run:
                self.pulllimit[loop] = self._calculate_pull_limit(self.cont_num[loop], target=loop)
            self.permcounters[loop] += self.cont_num[loop]

        self.debug('{0}th sec. Sub so far:{1},THIS run:{2}.'
                   'Comments so far:{3},THIS run:{4}'
                   .format(int((time.time() - start_time)), self.permcounters['submissions'],
                           self.cont_num['submissions'], self.permcounters['comments'],
                           self.cont_num['comments']))

        self.first_run = False

        self.debug(self.pulllimit['submissions'])
        self.debug(self.pulllimit['comments'])

        time.sleep(loop_timer)

    def _calculate_pull_limit(self, lastpullnum, target):
        """this needs to be done better"""
        add_more = {'submissions': 80, 'comments': 300}   # how many items above last pull number to pull next run

        if lastpullnum == 0:
            lastpullnum = results_limit / 2   # in case no new results are returned

        if self.pulllimit[target] - lastpullnum == 0:
            self.pulllimit[target] *= 2
        else:
            self.pulllimit[target] = lastpullnum + add_more[target]
        return int(self.pulllimit[target])

    def _get_new_comments_or_subs(self, target):
        if target == 'submissions':
            results = self.reddit_session.get_subreddit(watched_subreddit).get_new(limit=self.pulllimit[target],
                                                                                   place_holder=self.placeholder_id)
        if target == 'comments':
            results = self.reddit_session.get_comments(watched_subreddit, limit=self.pulllimit[target])
        new_submissions_list = []
        try:
            for submission in results:
                if submission.id not in self.processed_objects[target]:
                    new_submissions_list.append(submission)
                    self.processed_objects[target].append(submission.id)  # add to list of already processed submission
                    self.cont_num[target] += 1   # count the number of submissions processed each run
            self.placeholder_id = new_submissions_list[0].id
        except:
            print('ERROR:Cannot connect to reddit!!!')
        return new_submissions_list

    def _contentloop(self, target):
        new_submissions = self._get_new_comments_or_subs(target)

        if new_submissions:

            for new_submission in new_submissions:
                result_object = MatchedSubmissions(target=target, dsubmission=new_submission,
                                                   keyword_lists=self.redd_data)

            if result_object.matching_results:
                self.dispatch_nitifications(results_list=result_object.matching_results)
                result_object.purge_list()

    def dispatch_nitifications(self, results_list):
        for result in results_list:
            if result.msg_for_reply:
                targeted_submission = self.reddit_session.get_submission(result.args['dsubmission'].url)
                try:
                    reply = targeted_submission.comments[0].reply(result.msg_for_reply)
                    self.debug(reply.name)
                    self.debug('AntiBrigadeBot NOTICE sent')
                except:
                    self._log_this('Bot is BANNED in:{}, cant reply D:'.format(targeted_submission.subreddit))

            if result.msg_for_tweet:
                self.tweet_this(result.msg_for_tweet)
                self.debug('New Topic Match in: {}'.format(result.args['dsubmission'].subreddit))

    @staticmethod
    def debug(debugtext, level=DEBUG_LEVEL):
        if level >= 1:
            print('* {}'.format(debugtext))

    def _log_this(self, logtext):
        with open('LOG.txt', 'a') as logfile:
            logfile.write('{0}: {1}\n'.format(time.ctime(), logtext))
        self.debug('LOOGGED {}'.format(logtext))

    def tweet_this(self, msg):
        if len(msg) > 140:
            msg = msg[:139]
            self.debug('MSG exceeding 140 characters!!')
        try:
            self.twitter.update_status(status=msg)
            self.debug('TWEET SENT!!!')
        except:
            print('ERROR: couldnt update twitter status')

    def send_pm_to_owner(self, pm_text):
        try:
            self.reddit_session.send_message(self.bot_auth_info['REDDIT_PM_TO'], pm_text)
        except:
            print('ERROR:Cant send pm')


start_time = time.time()
bot1 = ReddBot(useragent=bot_agent_name, authfilename='ReddAUTH.json', datafilename='ReddData.json')
