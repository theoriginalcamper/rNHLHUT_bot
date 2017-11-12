import praw
import asyncio
import traceback
import re
import requests
import json

from datetime import timedelta
from time import time
from collections import OrderedDict

try:
	from asyncio import ensure_future
except ImportError:
	ensure_future = asyncio.async


'''
`sleep time` : time (in seconds) the bot sleeps before performing a new check
`time_until_message` : time (in seconds) a person has to add flair before a initial message is sent
`time_until_remove` : time (in seconds) after a message is sent that a person has to add flair before the post is removed and they have to resubmit it
`h_time_intil_remove` : Human Readable Version of time_until_remove
`post_grab_limit` : how many new posts to check at a time.
`add_flair_subject_line`, `add_flair_message` : Initial Message that tells a user that they need to flair their post
`remove_post_subject_line`, `remove_post_message`: Second message telling them to resubmit their post since they have not flaired in time
`no_flair` : Posts that still have a grace period to add a flair`
'''

sleep_time = 10
time_until_message = 20
time_until_remove = 600
h_time_until_remove = str(timedelta(seconds=time_until_remove))
post_grab_limit = 3
post_memory_limit = 15
posts_to_forget = post_memory_limit - post_grab_limit
subreddit_name = 'nhlhut'
current_moderators = []

add_flair_subject_line = "You have not flaired your post."
add_flair_message = ("[Your recent post]({post_url}) does not have any flair and will soon be removed.\n\n"
					 "Please add flair to your post. "
					 "**You reply to this message with 'Pack Pull', 'Team Advice', 'Discussion', 'PSA', 'Giveaway', 'Other', 'Video', 'PS4', 'Xbox One', 'News', 'GIF', 'Off Topic' and the bot will set the flair for you!**"
					 "If you do not add flair within **" + h_time_until_remove + "**, you will have to resubmit your post. "
					 "You can also add flair manually. Click [here](http://imgur.com/a/m3FI3) to view this helpful guide on how to manually flair your post. ")

remove_post_subject_line = "You have not flaired your post within the allotted amount of time."
remove_post_message = "[Your recent post]({post_url}) still does not have any flair and will remain removed, feel free to resubmit your post and remember to flair it once it is posted.*"

no_flair = OrderedDict()
user_agent = ("Auto flair moderator for nhlhut") # tells reddit the bot's purpose.

session = praw.Reddit('nhlhut_bot')
subreddit = session.subreddit(subreddit_name)


@asyncio.coroutine
def get_subreddit_settings(name):
	raise NotImplementedError("TODO: Subreddit settings")

@asyncio.coroutine
def get_moderators():
	'''Creates/updates the moderator list every day'''
	while True:
		try:
			yield from asyncio.sleep(3600)
			for moderator in session.subreddit(subreddit_name).moderator():
				if(moderator not in current_moderators):
					current_moderators.append(moderator.name)
					print("new moderator item added: %s" % current_moderators)
		except Exception as e:
			print(traceback.format_exc())
			print("{0}: {1}".format(type(e).__name__, str(e)))

	yield from get_moderators()

@asyncio.coroutine
def refresh_sesison():
	'''Re-logs in every n seconds'''
	while True:
		try:
			yield from asyncio.sleep(300)
			session = praw.Reddit('nhlhut_bot')
			subreddit = session.subreddit("nhlhut")
			print("Session refreshed")
		except Exception as e:
			print(traceback.format_exc())
			print("{0}: {1}".format(type(e).__name__, str(e)))

	yield from refresh_sesison()


@asyncio.coroutine
def inbox_stuff():
	# For lack of a better name
	'''Looks for mod invites, or if users have replied to the bot's message with a selected flair
	Refreshes every n seconds
	'''
	while True:
		try:
			for message in session.inbox.unread(): #look for inbox reply, handle
				if message.parent_id:
					if message.parent_id[3:] in no_flair:
						flaired = False
						post = session.submission(id=no_flair[message.parent_id[3:]])
						choices = post.flair.choices()
						for ch in choices:
							regex = re.compile('[^a-zA-Z]')
							if regex.sub('', message.body).lower() == regex.sub('', ch['flair_text']).lower():
								post.flair.select(ch['flair_template_id'], ch['flair_text'])
								flaired = True
								break
						if flaired:
							message.reply("Set Flair: **{}**".format(ch['flair_template_id']))
						else:
							message.reply("Flair **{}** not found".format(message.body))
					message.mark_read()

		except Exception as e:
			print(traceback.format_exc())
			print("{0}: {1}".format(type(e).__name__, str(e)))

		yield from asyncio.sleep(sleep_time)

	yield from inbox_stuff()


@asyncio.coroutine
def main():
	'''
	Checks to see if a post has a flair, sends the user a message after
	`time_until_message seconds`, and removes it if there is no flair after
	`time_until_remove` seonds. Approves post if a flair is added. Refreshes every n seconds.
	'''
	while True:
		# Checks to see if storing too many messages. If too many, forget posts_to_forget quantity
		if len(no_flair) >= post_memory_limit:
			i = 0
			while i < posts_to_forget:
				no_flair.popitem(0)
				i += 1

		try:
			for submission in subreddit.new(limit=post_grab_limit):
				# If message has no flair
				if ((submission.link_flair_text is None) and (submission.author.name not in current_moderators)):
					if((time() - submission.created_utc) > time_until_message) and submission.id not in no_flair.values(): #send first message, track
						final_add_flair_message = add_flair_message.format(post_url=submission.shortlink)
						print("Sent Message to : {}".format(submission.author))
						session.redditor(submission.author.name).message(add_flair_subject_line, final_add_flair_message)
						for msg in session.inbox.sent():
							if msg.body == final_add_flair_message:
								no_flair[msg.id] = submission.id
								continue

					if((time() - submission.created_utc) > time_until_remove): #remove, send removal message
						final_remove_post_message = remove_post_message.format(post_url=submission.shortlink)
						session.redditor(submission.author.name).message(remove_post_subject_line, final_remove_post_message)
						print("Removed {0.shortlink} of {0.author}'s".format(submission))
						for k in list(no_flair.keys()):
							if no_flair[k] == submission.id:
								no_flair.pop(k)
						submission.mod.remove()
						continue
						# Keeps track of how many posts the bot removed
						f = open('NumberRemoved','a')
						f.write('1\n')
						f.close()
				#
				if submission.id in no_flair.values() and submission.link_flair_text:
					submission.mod.approve()
					print("Approved {0.shortlink} of {0.author}'s".format(submission))
					for k in list(no_flair.keys()):
						if no_flair[k] == submission.id:
							no_flair.pop(k)
					continue
		except Exception as e:
			print(traceback.format_exc())
			print("{0}: {1}".format(type(e).__name__, str(e)))

		yield from asyncio.sleep(sleep_time)

	yield from main()

if __name__ == "__main__":
	# Puts main func into a loop and runs forever
	loop = asyncio.get_event_loop()

	print("Registering session refresh\n")
	ensure_future(refresh_sesison())

	print("\nGetting Moderators...\n")
	ensure_future(get_moderators())

	print("Registering Mod Invites\n")
	ensure_future(inbox_stuff())

	print("Registering Main\n")
	ensure_future(main())

	print("\nStarting...\n")
	loop.run_forever()

	loop.close()
