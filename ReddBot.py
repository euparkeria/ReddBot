__author__ = 'mekoneko'

import time
import praw
import json
import os
from random import choice
from twython import Twython

watched_subreddit = 'all'
results_limit = 200
results_limit_comm = 1000
bot_agent_names = ['redditlink bot v12']
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

    def readauthfile(self, authfilename):
        with open(authfilename, 'r', encoding='utf-8') as f:
            bot_auth_info = json.load(f)
        return bot_auth_info

    def readdatafile(self, datafilename):
        self.data_modified_time = os.stat(datafilename).st_mtime
        with open(datafilename, 'r', encoding='utf-8') as f:
            redd_data = json.load(f)
            redd_data['KEYWORDS'] = sorted(redd_data['KEYWORDS'], key=len, reverse=True)
            redd_data['SRSs'] = [x.lower() for x in redd_data['SRSs']]
        return redd_data


class MatchedSubmissions:

    matching_results = []

    def __init__(self, dsubmission, target, keyword_lists):
        self.is_srs = False
        self.keyword = False
        self.submission = dsubmission
        self.target = target
        _check_keywords = self._find_matching_keywords(target=target, dsubmission=dsubmission, keywords=keyword_lists['KEYWORDS'])
        _check_brigade = self._detect_brigade(dsubmission=dsubmission, srs_list=keyword_lists['SRSs'])

        if _check_keywords or _check_brigade:
            MatchedSubmissions.matching_results.append(self)

    @staticmethod
    def _get_text_body(target, dsubmission):
        if target == 'submissions':
            return dsubmission.title + dsubmission.selftext
        if target == 'comments':
            return dsubmission.body

    def _find_matching_keywords(self, target, dsubmission, keywords):
        body_text = self._get_text_body(target, dsubmission)
        for keyword in keywords:
            if keyword.lower() in body_text.lower():
                self.keyword = keyword
                return True
        return False

    def _detect_brigade(self, dsubmission, srs_list):
        subreddit = str(dsubmission.subreddit)
        if subreddit.lower() in srs_list and 'reddit.com' in dsubmission.url and not dsubmission.is_self:
            self.is_srs = True
            return True
        return False


class ReddBot:

    def __init__(self, useragent, authfilename, datafilename):
        self.args = {'useragent': useragent, 'authfilename': authfilename, 'datafilename': datafilename}
        self.pulllimit = {'submissions': results_limit, 'comments': results_limit_comm}
        self.first_run = True
        self.cont_num = {'comments': 0, 'submissions': 0}
        self.already_done = {'comments': [], 'submissions': []}
        self.loops = ['submissions']  # 'submissions' and 'comments' loops
        self.permcounters = {'comments': 0, 'submissions': 0}
        self.loop_counter = 0
        self.redd_data = {}
        self.bot_auth_info = {}
        self.reddit_session = None
        self.twitter = None
        self.config = ReadConfigFiles()

        while True:
            self.loop_counter += 1
            if self.loop_counter >= secondary_timer / loop_timer:
                self.debug('SEDONDARY LOOP')
                self.loop_counter = 0
            self._mainlooper()

    def _mainlooper(self):

        if os.stat(self.args['datafilename']).st_mtime > self.config.data_modified_time:  # check if config file has changed
            self.redd_data = self.config.readdatafile(self.args['datafilename'])
            self.bot_auth_info = self.config.readauthfile(self.args['authfilename'])
            self.debug('CONFIG FILES REREAD!')
            bot_session = ConnectSocialMedia(self.bot_auth_info, useragent=self.args['useragent'])
            self.reddit_session = bot_session.reddit_session
            self.twitter = bot_session.twitter_session
            self.debug('RECONNECTED!')

        self.cont_num['submissions'], self.cont_num['comments'] = 0, 0

        for loop in self.loops:
            self.contentloop(target=loop)
            buffer_reset_lenght = self.pulllimit[loop] * 10
            if len(self.already_done[loop]) >= buffer_reset_lenght:
                self.already_done[loop] = self.already_done[loop][int(len(self.already_done[loop]) / 2):]
                self.debug('DEBUG:buffers LENGHT after trim {0}'.format(len(self.already_done[loop])))
            if not self.first_run:
                self.pulllimit[loop] = self._calculate_pull_limit(self.cont_num[loop], target=loop)
            self.permcounters[loop] += self.cont_num[loop]

        self.debug('Running for :{0} secs. Submissions so far: {1}, THIS run: {2}.'
                   ' Comments so  far:{3}, THIS run:{4}'
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

        res_diff = self.pulllimit[target] - lastpullnum
        if res_diff == 0:
            self.pulllimit[target] *= 2
        else:
            self.pulllimit[target] = lastpullnum + add_more[target]
        return int(self.pulllimit[target])

    def contentloop(self, target):
        try:
            if target == 'submissions':
                results = self.reddit_session.get_subreddit(watched_subreddit).get_new(limit=self.pulllimit[target])
            if target == 'comments':
                results = self.reddit_session.get_comments(watched_subreddit, limit=self.pulllimit[target])
        except:
            print('ERROR: Cant connect to reddit, may be down.')
        #try:
        for submission in results:
            if submission.id not in self.already_done[target]:
                sub = MatchedSubmissions(target=target, dsubmission=submission, keyword_lists=self.redd_data)
                self.already_done[target].append(submission.id)  # add to list of already processed submissions
                self.cont_num[target] += 1   # count the number of submissions processed each run

        self.dispatch_nitifications(results_list=sub.matching_results)

        MatchedSubmissions.matching_results = []
        #except:
            #print('content loop error')

    def dispatch_nitifications(self, results_list):
        for result in results_list:
            msg = 0
            if result.is_srs:
                s = self.reddit_session.get_submission(result.submission.url)
                s.comments[0].reply('#**NOTICE**: ReddBot detected this comment/thread has been targeted by a downvote'
                                    ' brigade from [/r/{0}]({1}) \n--------------------\n *{2}* \n\n'
                             .format(result.submission.subreddit, result.submission.short_link, choice(self.redd_data['quotes'])))
                if result.keyword:
                    msg = 'ATTENTION: possible reactionary brigade from /r/{1} regarding #{0}: {2} #reddit'\
                                .format(result.keyword, result.submission.subreddit, result.submission.short_link)
            elif result.keyword:
                msg = 'Submission regarding #{0} posted in /r/{1} : {2} #reddit'.format(
                    result.keyword, result.submission.subreddit, result.submission.short_link)
            if msg:
                self.tweet_this(msg)


    @staticmethod
    def debug(debugtext, level=DEBUG_LEVEL):
        if level >= 1:
            print('*DEBUG: {}'.format(debugtext))

    def tweet_this(self, msg):

        if len(msg) > 140:
            msg = msg[:139]
            self.debug('MSG exceeding 140 characters!!')
        try:
            self.twitter.update_status(status=msg)
            self.debug('Tweet sent!!!')
        except:
            print('ERROR: couldnt update twitter status')


start_time = time.time()
bot1 = ReddBot(useragent=choice(bot_agent_names), authfilename='ReddAUTH.json', datafilename='ReddData.json')
