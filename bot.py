"""
bot for hangouts

some portions are copied from YellowPapaya/hangouts-bot
"""
import asyncio
import sys
import json

import hangups

import handler
import utils


class Bot:
    """bot for hangouts"""

    def __init__(self):
        self.cookies = hangups.get_auth_stdin("token.txt", True)
        self.client = hangups.Client(self.cookies)

        with open("reply_data.json", "r") as replies_file:
            self.reply_data = json.load(replies_file)
        self.handler = handler.Handler(self, self.reply_data)
        self.connected = asyncio.Event()

        # to prevent replying to self
        self.recent_meeper_messages = []
        self.sending_lock = asyncio.Lock()

    def run(self):
        """main loop for running bot"""
        self.client.on_connect.add_observer(self._on_connect)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.client.connect())
        sys.exit(0)

    async def _on_connect(self):
        """called when bot connects to hangouts"""
        self._user_list, self._conv_list = (
            await hangups.build_user_conversation_list(self.client)
        )
        self._conv_list.on_event.add_observer(self._on_event)
        self.connected.set()
        print("Meeper connected!")

    async def _on_event(self, event):
        """called when there is an event in hangouts"""
        if (isinstance(event, hangups.ChatMessageEvent)):
            # sometimes lag between a message getting added and getting received
            # is too big, so this needs to get locked to avoid replying to itself
            async with self.sending_lock:
                if event.text in self.recent_meeper_messages:
                    # to avoid triggering itself
                    self.recent_meeper_messages.remove(event.text)
                    return

            # only reply to conversations
            # in hangouts_data.reply_to_conv in the json
            if self.conv_is("reply_to", self.get_conv(event.conversation_id)):
                asyncio.ensure_future(self.handler.handle_message(event, self))

    async def get_messages(self, conv_name, batch_size=2500):
        """
        gets all messages from the conversation and returns in a list of strings
        formatted name :: date :: message
        :: is used because it is very uncommon in messages
        """
        # cant load unless connected
        await self.connected.wait()

        # setup
        conv = self.get_conv(conv_name)
        events = await conv.get_events()
        event = events[-1]
        messages = []
        last_timestamp = event.timestamp
        batch_count = 1

        # loops through untill the timestamp is greater
        # since conv.get_events loops when it runs out for some reason
        # this will result in an infinite loop if batch_size > total messages in conv
        while True:
            print(f"getting messages from {conv_name}, batch {batch_count}")
            events = await conv.get_events(event.id_, max_events=batch_size)
            event = events[0]
            if event.timestamp > last_timestamp:
                break

            # this is probably really ineffecient
            # but it was the best i could come up with
            messages = [
                " ::".join(
                    conv.get_user(event.user_id).first_name,
                    utils.datetime_to_string(event.timestamp),
                    event.text
                )
                for event in events
                if (isinstance(event, hangups.ChatMessageEvent))
            ] + messages
            last_timestamp = event.timestamp
            batch_count += 1
        return messages

    def get_conv(self, name):
        """gets conversation by name or id"""
        if name in self.reply_data["hangouts_data"]["conversations"]:
            conv_id = self.reply_data["hangouts_data"]["conversations"][name]["id"]
        else:
            conv_id = name
        return self._conv_list.get(conv_id)

    def user_is(self, property_, user, default=False):
        """Checks if the user has the property in self.reply_data"""
        for other_user_name, other_user in self.reply_data["hangouts_data"]["users"].items():
            if other_user["id"] == user.id_[0]:
                return other_user.get(property_, default)
        return False

    def conv_is(self, property_, conv, default=False):
        """Checks if the conv has the property in self.reply_data"""
        for other_conv_name, other_conv in self.reply_data["hangouts_data"]["conversations"].items():
            if other_conv["id"] == conv.id_:
                return other_conv.get(property_, default)

    async def send_message(self, *messages, conv="log"):
        """sends the given messages one at a time to conv"""
        # cant send unless connected
        await self.connected.wait()

        # to get conversation if conv_id or name is provided
        if not isinstance(conv, hangups.conversation.Conversation):
            conv = self.get_conv(conv)

        # actually sending the message
        async with self.sending_lock:
            for message in messages:
                try:
                    await conv.send_message(hangups.ChatMessageSegment.from_str(message))
                    self.recent_meeper_messages.append(message)
                except hangups.exceptions.NetworkError as network_error:
                    # in case of hitting message limit or other random errors
                    # that i can't really deal with
                    print(
                        "error when sending messages",
                        network_error, sep="\n"
                    )
                    return

    async def quit(self):
        """kills the bot"""
        await self.send_message("quitting", conv="log")
        await self.client.disconnect()
