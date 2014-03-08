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
bot_agent_names = ['Reddit word cloud 1.2', 'reddit topic collector 0.5', 'alpaSix search crawler 20130402r8']
loop_timer = 60
buffer_reset_lenght = 2000
DEBUG_LEVEL = 1


class ReddBot:

    def readconfig(self, authfilename, datafilename):
        self.data_modified_time = os.stat(datafilename).st_mtime
        with open(datafilename, 'r', encoding='utf-8') as f:
            redd_data = json.load(f)
            redd_data['KEYWORDS'] = sorted(redd_data['KEYWORDS'], key=len, reverse=True)
            redd_data['SRSs'] = [x.lower() for x in redd_data['SRSs']]
            self.debug(redd_data['KEYWORDS'])
            self.debug(redd_data['SRSs'])
        with open(authfilename, 'r', encoding='utf-8') as f:
            bot_auth_info = json.load(f)
        return redd_data, bot_auth_info

    @staticmethod
    def connect_to_socialmedia(authinfo, useragent):
        r = praw.Reddit(user_agent=useragent, api_request_delay=1)
        r.login(authinfo['REDDIT_BOT_USERNAME'], authinfo['REDDIT_BOT_PASSWORD'])

        t = Twython(authinfo['APP_KEY'], authinfo['APP_SECRET'],
                    authinfo['OAUTH_TOKEN'], authinfo['OAUTH_TOKEN_SECRET'])
        return r, t

    def __init__(self, useragent, authfilename, datafilename):
        self.data_modified_time = 0
        self.pulllimit = {'submissions': results_limit, 'comments': results_limit_comm}
        self.first_run = True
        self.cont_num = {'comments': 0, 'submissions': 0}
        self.already_done = {'comments': [], 'submissions': []}
        self.loops = ['submissions']  # 'submissions' and 'comments' loops
        self.permcounters = {'comments': 0, 'submissions': 0}

        while True:
            try:
                if os.stat(datafilename).st_mtime > self.data_modified_time:  # check if config file has changed
                    self.redd_data, self.bot_auth_info = self.readconfig(authfilename, datafilename)
                    self.reddit_session, self.twitter = self.connect_to_socialmedia(self.bot_auth_info,
                                                                                    useragent=useragent)

                self.cont_num['submissions'] = 0
                self.cont_num['comments'] = 0

                for loop in self.loops:
                    self.contentloop(target=loop)
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
            except:
                print('HTTP Error')
            time.sleep(loop_timer)
            
    def _calculate_pull_limit(self, lastpullnum, target):
        """this needs to be done better"""
        add_more = {'submissions': 80, 'comments': 300}   # how many items above last pull number to pull next run

        if not lastpullnum:
            lastpullnum = self.pulllimit[target] - 1   # in case no new results are returned

        res_diff = self.pulllimit[target] - lastpullnum
        if res_diff == 0:
            self.pulllimit[target] *= 2
        else:
            self.pulllimit[target] = lastpullnum + add_more[target]
        return int(self.pulllimit[target])

    def contentloop(self, target):
        if target == 'submissions':
            results = self.reddit_session.get_subreddit(watched_subreddit).get_new(limit=self.pulllimit[target])
        if target == 'comments':
            results = self.reddit_session.get_comments(watched_subreddit, limit=self.pulllimit[target])

        for content in results:
            if content.id not in self.already_done[target]:
                for manip in self.mastermanipulator(target=target):
                    return_text = manip(content)
                    if return_text is not False:
                        print(return_text)
                self.already_done[target].append(content.id)  # add to list of already processed submissions
                self.cont_num[target] += 1   # count the number of submissions processed each run

    @staticmethod
    def debug(debugtext, level=DEBUG_LEVEL):
        if level >= DEBUG_LEVEL:
            print('*DEBUG: {}'.format(debugtext))

    def mastermanipulator(self, target):

        def topicmessanger(dsubmission):
            msgtext = {'comments': "Comment concerning #{0} posted in /r/{1} {2} #reddit"}

            if target == 'submissions':
                op_text = dsubmission.title + dsubmission.selftext
            if target == 'comments':
                op_text = dsubmission.body
            for item in self.redd_data['KEYWORDS']:
                if item.lower() in op_text.lower():
                    if target == 'comments':
                        msg = msgtext['comments']\
                            .format(item, dsubmission.subreddit, dsubmission.permalink)

                    elif target == 'submissions':
                        subreddit = str(dsubmission.subreddit)
                        if subreddit.lower() in self.redd_data['SRSs'] and 'reddit.com' in dsubmission.url and not dsubmission.is_self:
                            msg = 'ATTENTION: possible reactionary brigade from /r/{1} regarding #{0}: {2} #reddit'\
                                .format(item, dsubmission.subreddit, dsubmission.short_link)
                            try:
                                s = self.reddit_session.get_submission(dsubmission.url)
                                s.comments[0].reply('##NOTICE: *This comment/thread has just been targeted'
                                                    ' by a downvote brigade from [/r/{0}]({1})* \n\n '
                                                    '*I am a bot, please PM if this message is a mistake.* \n\n'
                                                    .format(dsubmission.subreddit, dsubmission.short_link))
                            except:
                                print('brigade warning failed')
                        else:
                            msg = 'Submission regarding #{0} posted in /r/{1} : {2} #reddit'.format(
                                item, dsubmission.subreddit, dsubmission.short_link)
                    if len(msg) > 140:
                        msg = msg[:-8]
                        self.debug('MSG exceeding 140 characters!!')
                    #self.reddit_session.send_message(bot_auth_info['REDDIT_PM_TO'], 'New {0} discussion!'.format(item), msg)
                    self.twitter.update_status(status=msg)

                    return 'New Topic match in:{0}, keyword:{1}'.format(dsubmission.subreddit, item)
            return False

        def nothing(nothing):
            return False

        '''
        IF YOU WANT TO DISABLE A BOT FEATURE for a specific loop REMOVE IT FROM THE DICTIONARY BELLOW
        '''
        returnfunctions = {'comments': [topicmessanger, nothing], 'submissions': [topicmessanger, nothing]}
        return returnfunctions[target]

start_time = time.time()
bot1 = ReddBot(useragent=choice(bot_agent_names), authfilename='ReddAUTH.json', datafilename='ReddData.json')
