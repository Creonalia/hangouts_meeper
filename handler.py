import asyncio
import random
import re
import utils

import hangups


class Handler:
    """contains most of the logic for replying"""
    def __init__(self, bot, reply_data):
        self.status = {
            "active": True,
            "history": True,
            "last_history": slice(1, 2),
            "grep_start": 0,
            "max_grep": 20,
        }

        self.reply_data = reply_data
        for group_name in self.reply_data["reply_groups"]:
            self.status[group_name] = True

        # to prevent reading and writing to history file simultaneously
        self.history_lock = asyncio.Lock()
        asyncio.ensure_future(self.load_history(bot))

    async def handle_message(self, event, bot):
        conv = bot.get_conv(event.conversation_id)
        user = conv.get_user(event.user_id)

        # check for and run commands
        messages = await self.run_commands(event.text)
        if messages:
            await bot.send_message(*messages, conv=conv)

        # admin commands (like shutting down)
        if bot.user_is("admin", user):
            await self.run_admin_commands(event, bot)

        # the bot sending messages marks them as read
        # so this gives other people a way to notify you
        if self.reply_data["notify_keyword"] in event.text.lower():
            await bot.send_message(f"message from {user.full_name}: {event.text}", conv="log")

        # respond to messages
        for group_name, reply_group in self.reply_data["reply_groups"].items():
            if "keyword" in reply_group:
                # separate ifs to prevent keyerror
                if re.findall(reply_group["keyword"], utils.clean(event.text, split=False)):
                    await bot.send_message(*self.get_random_reply(reply_group), conv=conv)
                    break
        if self.status["active"] and bot.user_is("reply_to", user):
            await bot.send_message(
                *await self.reply_to_user(event.text), conv=conv
            )

    async def run_commands(self, raw_text):
        """
        Run various commands

        history - get history at line # of history file if given otherwise send random
        context - 10 messages before the last history sentence
        more - 10 messages after the last history sent
        grep - search for the rest of the message in the history file
        """
        text = utils.command_parser(raw_text)
        word = next(text)

        if word == "context":
            return await self.get_history(self.status["last_history"].start - 10, 10)

        elif word == "more":
            return await self.get_history(self.status["last_history"].stop, 10)

        elif word == "history":
            word = next(text)
            if word.isdigit():
                return await self.get_history(int(word))
            else:
                return await self.get_history()

        elif word == "grep":
            query = raw_text[5:]
            async with self.history_lock:
                with open(self.reply_data["history_file"]) as message_file:
                    # :: is used as a seperator between sender, datetime, and message in generated history files
                    # this attempts to prevent repeating messages sent in previous greps
                    results = [
                        f"{index}: {line}"
                        for index, line in list(enumerate(message_file.readlines()))[self.status["grep_start"]:]
                        if query in line and line.count("::") < 4
                    ]
            result_count = len(results)
            if result_count > self.status["max_grep"]:
                results = results[:self.status["max_grep"]]
            return [
                f"{result_count} matches found for {query}",
                *results,
                f"done sending {len(results)}/{result_count} results for {query}",
            ]

    async def run_admin_commands(self, event, bot):
        """
        runs administrative / dev commands

        ping - replies pinged, used to check it is online
        status - replies with everything in self.status (mostly config options)
        reply - replies using reply_to_user
        set - edits self.status
        quit - kills the bot
        """
        split_text = utils.command_parser(event.text)
        word = next(split_text)

        if word == "ping":
            await bot.send_message("pinged", conv="log")

        elif word == "status":
            await bot.send_message(utils.join_items(
                *self.status.items(), description_mode="short", end="",
                newlines=0
            ), conv="log")

        elif word == "reply":
            await bot.send_message(
                *await self.reply_to_user(split_text.send("remaining")),
                conv="log"
            )

        if word == "set":
            await bot.send_message(self.set_status(next(split_text), next(split_text)), conv="log")

        elif word == "quit":
            await bot.quit()

    def set_status(self, property_, new_value):
        """
        sets self.status

        takes strings for both regardless of type
        because its expecting values from text input
        currently only works with ints and bools
        """

        if property_ not in self.status:
            return f"invalid status to set {property_}"
        property_type = type(self.status[property_])

        if property_type == bool:
            new_value = new_value[0] == "t"
            self.status[property_] = new_value
            return "set"

        elif property_type == int:
            if new_value.isdigit():
                self.status[property_] = int(new_value)
                return "set"
            else:
                return "invalid value"

        else:
            return "you cannot set that"

    async def reply_to_user(self, raw_text):
        """sends replies from reply)data based on the message"""
        text = utils.clean(raw_text, split=False)
        replies = []

        # check for keywords
        for keyword_regex, responses in self.reply_data["keywords"].items():
            if re.findall(keyword_regex, text):
                replies.append(random.choice(responses))
                break

        # check for keywords for reply groups
        if not replies:
            for group_name, reply_group in self.reply_data["reply_groups"].items():
                if random.randint(0, 100) <= reply_group["chance"] and self.status[group_name]:
                    replies += self.get_random_reply(reply_group)
                    break

        # maybe send random chunk of history
        if not replies and random.randint(1, 10) < 3 and self.status["history"]:
            replies += await self.get_history()

        # reply in all caps if text is all caps
        if raw_text.isupper():
            replies = [reply.upper() for reply in replies]
        return replies

    def get_random_reply(self, reply_group):
        """gets a random reply from the given reply group depending on type"""
        group_type = reply_group["type"]
        if group_type == "single":
            return [random.choice(reply_group["replies"]), ]
        elif group_type == "group":
            return random.choice(reply_group["replies"])

    async def get_history(self, start=None, size=5):
        """returns history at line # start if given, otherwise returns random"""
        async with self.history_lock:
            with open(self.reply_data["history_file"]) as message_file:
                messages = message_file.readlines()

                # random slice if none given
                if start is None:
                    start = random.randint(0, len(messages) - size)
                slice_ = slice(
                    utils.clamp(start, 0, len(messages) - size),
                    utils.clamp(start + size, size, len(messages)),
                )

                # need to save the slice for using other commands like context
                self.status["last_history"] = slice_
                return messages[slice_]

    async def load_history(self, bot):
        """loads chat history of given conversations"""
        for conv_name, conv in self.reply_data["hangouts_data"]["conversations"].items():
            if not conv.get("load_history", False):
                continue
            try:
                messages = await bot.get_messages(conv_name)
            except hangups.exceptions.NetworkError as network_error:
                # started getting 401 Unauthorized for no identifiable reason
                # so this just gives up since i can't find a fix
                print(
                    f"error when getting history for {conv_name}",
                    network_error, sep="\n"
                )
                return

            async with self.history_lock:
                with open(f"messages_{conv_name}.txt", "w") as history_file:
                    history_file.write("\n".join(messages))
        print("done loading history")
