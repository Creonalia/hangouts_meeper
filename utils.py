"""
assorted general purpose functions

a lot of this is copied over from my code in YellowPapaya/hangouts-bot
"""
import inspect
import datetime
import pytz

current_timezone = pytz.timezone("US/Pacific")


def datetime_to_string(datetime_):
    return datetime_.astimezone(current_timezone).strftime("%b %d, %Y %I:%M %p")


def convert_items(items, type_, default=""):
    """converts items to type or replaces with default"""
    for i in range(len(items)):
        try:
            items[i] = type_(items[i])
        except ValueError:
            items[i] = default
    return items


def join_items(
    *items, separator="\n", description_mode=None,
    start="", end="", newlines=1
):
    """
    joins items using separator, ending with end and newlines

    Args:
        *items - the things to join
        separator - what seperates items
        description_mode - what mode to use for description
        start - what to start the string with
        end - what to end the string with
        newlines - how many newlines to add after end

    Returns a string
    """

    output_list = []
    if description_mode:
        for item in items:
            output_list.append(description(
                *(item if item else ""), mode=description_mode,
                newlines=0
            ))

    else:
        output_list = convert_items(list(items), type_=str)
    output_list = [item.strip() for item in output_list]
    output_text = separator.join(output_list).strip()
    output_text += "" if output_text.endswith(end) else end
    output_text = start + newline(output_text, newlines)
    return output_text


def newline(text, number=1):
    """returns text with exactly number newlines at the end"""
    return text.strip() + ("\n" * number)


def description(name, *description, mode="short", end="\n", newlines=1):
    """
    string formatting function

    short: formats, like, this
    long:
        formats
        like
        this
    """
    # prevents errors
    description = convert_items(list(description), str)

    if mode == "short":
        description = join_items(
            *description, separator=", ", end=end, newlines=0)
        full_description = f"{name}: {description}"
    elif mode == "long":
        description.insert(0, f"{name.title()}:")
        full_description = join_items(
            *description, separator="\n\t", end=end, newlines=0)
    else:
        raise ValueError(f"mode {mode} does not exist for descriptions")
    return newline(full_description, newlines)


# processing strings
def clean(text, split=True):
    """cleans user input and returns as a list"""
    if text:
        split_text = text.strip().lower().split()
        # splits and joins to insure no extra whitespace
        return split_text if split else " ".join(split_text)
    else:
        return [""]


def clamp(value, min_value, max_value):
    """makes value equal max if greater than max and min if less than min"""
    return max(min_value, min(value, max_value))


def command_parser(command_text):
    """
    returns a generator of commands
    generator yields empty string if there are no more commands
    """
    commands = clean(command_text)
    current_index = 0
    val = None
    while True:
        if isinstance(val, int):
            current_index += val
            current_index = clamp(current_index, 0, len(commands))
            item = get_item(commands, indexes=(current_index, ))
        elif val == "remaining":
            item = join_items(
                *commands[current_index:], separator=" ", newlines=0)
        elif val == "all":
            item = commands
        elif val == "raw":
            item = command_text
        else:
            item = get_item(commands, indexes=(current_index, ))
            current_index += 1
        val = yield item


# get things without errors
def get_item(sequence, indexes=(0, ), default=""):
    """
    Retrives the items at the indexes in sequence
    defaults to default if the item does not exist
    """
    if inspect.isgenerator(sequence):
        return next(sequence)
    items = []
    for index in indexes:
        try:
            item = sequence[index]
        except IndexError:
            item = default

        if len(indexes) == 1:
            items = item
        else:
            items.append(item)
    return items
