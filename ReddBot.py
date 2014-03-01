__author__ = 'mekoneko'

import time
import praw
import json

from twython import Twython

watched_subreddit = 'all'
results_limit = 200
results_limit_comm = 1000
bot_agent_name = 'reddit topic crawler v0.8'
loop_timer = 60
buffer_reset_lenght = 4000
DEBUG_LEVEL = 1


class ReddBot:

    def readconfig(self, authfilename, datafilename):
        with open(datafilename, 'r', encoding='utf-8') as f:
            ReddData = json.load(f)
            ReddData['KEYWORDS'] = sorted(ReddData['KEYWORDS'], key=len, reverse=True)
            ReddData['SRSs'] = [x.lower() for x in ReddData['SRSs']]
            self.debug(ReddData['KEYWORDS'], DEBUG_LEVEL)
            self.debug(ReddData['SRSs'], DEBUG_LEVEL)
        with open(authfilename, 'r', encoding='utf-8') as f:
            BotAuthInfo = json.load(f)
        return ReddData, BotAuthInfo

    def connect_to_socialmedia(self, authinfo, useragent):
        r = praw.Reddit(user_agent=useragent, api_request_delay=1)
        r.login(authinfo['REDDIT_BOT_USERNAME'], authinfo['REDDIT_BOT_PASSWORD'])

        t = Twython(authinfo['APP_KEY'], authinfo['APP_SECRET'],
                    authinfo['OAUTH_TOKEN'], authinfo['OAUTH_TOKEN_SECRET'])
        return r, t

    def __init__(self, useragent, authfilename, datafilename):
        self.pulllimit = {'submissions': results_limit, 'comments': results_limit_comm}
        self.first_run = True
        self.cont_num = {'comments': 0, 'submissions': 0}
        self.already_done = {'comments': [], 'submissions': []}
        self.loops = ['submissions']  # 'submissions' and 'comments' loops
        self.permcounters = {'comments': 0, 'submissions': 0}
        self.ReddData, self.BotAuthInfo = self.readconfig(authfilename, datafilename)
        self.reddit_session, self.twitter = self.connect_to_socialmedia(self.BotAuthInfo, useragent=useragent)

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

                self.debug('Running for :{0} secs. Submissions so far: {1}, THIS run: {2}. Comments so  far:{3}, THIS run:{4}'
                           .format(int((time.time() - start_time)), self.permcounters['submissions'],
                                   self.cont_num['submissions'], self.permcounters['comments'],
                                   self.cont_num['comments']), DEBUG_LEVEL)

                self.first_run = False

                self.debug(self.pulllimit['submissions'], DEBUG_LEVEL)
                self.debug(self.pulllimit['comments'], DEBUG_LEVEL)
            except:
                print('HTTP Error')
            time.sleep(loop_timer)
            
    def calculatepulllimit(self, lastpullnum, target):
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
                self.already_done[target].append(content.id)  # add to list of already processed submissions
                self.cont_num[target] += 1   # count the number of submissions processed each run

    @staticmethod
    def debug(debugtext, level):
        if level >= DEBUG_LEVEL:
            print('*DEBUG: {}'.format(debugtext))

    def mastermanipulator(self, target):

        def topicmessanger(dsubmission):
            msgtext = {'comments': "Comment concerning #{0} posted in /r/{1} {2} #reddit" }

            if target == 'submissions':
                op_text = dsubmission.title + dsubmission.selftext
            if target == 'comments':
                op_text = dsubmission.body
            for item in self.ReddData['KEYWORDS']:
                if item.lower() in op_text.lower():
                    if target == 'comments':
                        msg = msgtext['comments']\
                            .format(item, dsubmission.subreddit, dsubmission.permalink)
                    else:
                        subreddit = str(dsubmission.subreddit)
                        if subreddit.lower() in self.ReddData['SRSs']:
                            msg = 'ATTENTION: possible reactionary brigade from /r/{1} regarding #{0}: {2} #reddit'\
                                .format(item, dsubmission.subreddit, dsubmission.short_link)
                        else:
                            msg = 'Submission regarding #{0} posted in /r/{1} : {2} #reddit'.format(
                                item, dsubmission.subreddit, dsubmission.short_link)
                    if len(msg) > 140:
                        msg = msg[:-7]
                        self.debug('MSG exceeding 140 characters!! Dropping!')                    
                    #self.reddit_session.send_message(BotAuthInfo['REDDIT_PM_TO'], 'New {0} discussion!'.format(item), msg)
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
bot1 = ReddBot(useragent=bot_agent_name, authfilename='ReddAUTH.json', datafilename='ReddData.json')
