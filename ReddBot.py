__author__ = 'mekoneko'

import time
import praw
import json
import requests
from twython import Twython

watched_subreddit = 'all'
results_limit = 200
results_limit_comm = 1000
bot_agent_name = 'reddit topic crawler v0.7'
loop_timer = 45
buffer_reset_lenght = 8000
DEBUG_LEVEL = 1


with open('ReddDATA.json', 'r', encoding='utf-8') as f:
    ReddData = json.load(f)

with open('ReddAUTH.json', 'r', encoding='utf-8') as f:
    BotAuthInfo = json.load(f)


twitter = Twython(BotAuthInfo['APP_KEY'], BotAuthInfo['APP_SECRET'],
                  BotAuthInfo['OAUTH_TOKEN'], BotAuthInfo['OAUTH_TOKEN_SECRET'])


class ReddBot:

    def connect_to_reddit(self, rusername, rpassword, useragent):
        r = praw.Reddit(user_agent=useragent, api_request_delay=1)
        r.login(rusername, rpassword)
        return r

    def __init__(self, username, password, useragent):
        self.pulllimit = {'submissions': results_limit, 'comments': results_limit_comm}
        self.first_run = True
        self.cont_num = {'comments': 0, 'submissions': 0}
        self.already_done = {'comments': [], 'submissions': []}
        self.loops = ['submissions'] # 'submissions' and 'comments' loops
        self.permcounters = {'comments': 0, 'submissions': 0}

        self.reddit_session = self.connect_to_reddit(username, password, useragent)

        while True:
            try:
                self.cont_num['submissions'] = 0
                self.cont_num['comments'] = 0

                for loop in self.loops:
                    self.contentloop(target=loop)
                    if len(self.already_done[loop]) >= buffer_reset_lenght:
                        self.already_done[loop] = self.already_done[loop][int(len(self.already_done[loop])/2):]
                        self.debug('DEBUG:buffers LENGHT after trim {0}'.format(len(self.already_done[loop])), DEBUG_LEVEL)
                    if not self.first_run:
                        self.pulllimit[loop] = self.calculatepulllimit(self.cont_num[loop], target=loop)
                    self.permcounters[loop] += self.cont_num[loop]

                self.debug('Running for :{0} secs. Submissions so far: {1}, THIS run: {2}.Comments so  far:{3}, THIS run:{4}'
                      .format(int((time.time() - start_time)), self.permcounters['submissions'], self.cont_num['submissions'],
                            self.permcounters['comments'], self.cont_num['comments']), DEBUG_LEVEL)

                self.first_run = False

                self.debug(self.pulllimit['submissions'], DEBUG_LEVEL)
                self.debug(self.pulllimit['comments'], DEBUG_LEVEL)
            except:
                print('HTTP Error')
            time.sleep(loop_timer)

    def calculatepulllimit(self, lastpullnum, target):
        """this needs to be done better"""
        if target == 'submissions':
            add_more = 80
        elif target == 'comments':
            add_more = 300
        if lastpullnum == 0:
            lastpullnum = self.pulllimit[target] - 1 #in case no new results are returned

        res_diff = self.pulllimit[target] - lastpullnum
        if res_diff == 0:
            self.pulllimit[target] *= 2
        else:
            self.pulllimit[target] = lastpullnum + add_more
        return int(self.pulllimit[target])

    def contentloop(self, target):
        if target == 'submissions':
            subreddits = self.reddit_session.get_subreddit(watched_subreddit)
            results = subreddits.get_new(limit=self.pulllimit[target])
        if target == 'comments':
            results = self.reddit_session.get_comments(watched_subreddit, limit=self.pulllimit[target])

        for content in results:
            if content.id not in self.already_done[target]:
                for manip in self.mastermanipulator(target=target):
                    return_text = manip(content)
                    if return_text is not False:
                        print(return_text)
                self.already_done[target].append(content.id) #add to list of already processed submissions
                self.cont_num[target] += 1 #count the number of submissions processed each run

    @staticmethod
    def debug(debugtext, level):
        if level >= DEBUG_LEVEL:
            print('*DEBUG: {}'.format(debugtext))

    def mastermanipulator(self, target):


        def topicmessanger(dsubmission):
            if target == 'submissions':
                op_text = dsubmission.title.lower() + dsubmission.selftext.lower()
            else:
                op_text = dsubmission.body.lower()
            for item in ReddData['KEYWORDS']:
                if item.lower() in op_text:
                    if target == 'comments':
                        msg = 'Comment concerning #{0} posted in /r/{1} : {2} #reddit'.format(item, dsubmission.subreddit, dsubmission.permalink)
                    else:
                        msg = 'Submission concerning #{0} posted in /r/{1} : {2} #reddit'.format(item, dsubmission.subreddit, dsubmission.short_link)
                    #self.reddit_session.send_message(BotAuthInfo['REDDIT_PM_TO'], 'New {0} discussion!'.format(item), msg)
                    twitter.update_status(status=msg)
                    return 'New Topic match in:{}'.format(dsubmission.subreddit)
            return False

        def nothing(nothing):
            return False

        '''
        IF YOU WANT TO DISABLE A BOT FEATURE for a specific loop REMOVE IT FROM THE LIST BELLOW
        '''
        if target == 'comments':
            return [topicmessanger, nothing]
        if target == 'submissions':
            return [topicmessanger, nothing]

start_time = time.time()
bot1 = ReddBot(BotAuthInfo['REDDIT_BOT_USERNAME'], BotAuthInfo['REDDIT_BOT_PASSWORD'], bot_agent_name)


