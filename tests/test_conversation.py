import pytest

from nova.ai import AIError, Message
from nova.conversation import Conversation


class FakeResponder:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.error = None
        self.calls = []

    def reply(self, messages):
        self.calls.append(list(messages))
        if self.error:
            raise self.error
        return self.replies.pop(0)


def test_ask_returns_reply_and_records_turn():
    conversation = Conversation(FakeResponder(["Hello!"]), max_turns=5)
    assert conversation.ask("Hi") == "Hello!"
    assert conversation.history == (Message("user", "Hi"), Message("assistant", "Hello!"))


def test_follow_up_sends_previous_turns():
    responder = FakeResponder(["Kathmandu", "About 1.5 million"])
    conversation = Conversation(responder, max_turns=5)
    conversation.ask("Capital of Nepal?")
    conversation.ask("Its population?")
    assert responder.calls[1] == [
        Message("user", "Capital of Nepal?"),
        Message("assistant", "Kathmandu"),
        Message("user", "Its population?"),
    ]


def test_history_keeps_only_last_turns():
    conversation = Conversation(FakeResponder(["a1", "a2", "a3"]), max_turns=2)
    for question in ["q1", "q2", "q3"]:
        conversation.ask(question)
    assert [m.text for m in conversation.history] == ["q2", "a2", "q3", "a3"]


def test_failed_turn_leaves_history_unchanged():
    responder = FakeResponder(["first answer"])
    conversation = Conversation(responder, max_turns=5)
    conversation.ask("first")
    before = conversation.history

    responder.error = AIError("network down")
    with pytest.raises(AIError):
        conversation.ask("second")

    assert conversation.history == before


def test_input_is_stripped():
    responder = FakeResponder(["ok"])
    Conversation(responder, max_turns=5).ask("  hello \n")
    assert responder.calls[0] == [Message("user", "hello")]


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_input_is_rejected_without_calling_model(text):
    responder = FakeResponder()
    with pytest.raises(ValueError):
        Conversation(responder, max_turns=5).ask(text)
    assert responder.calls == []


def test_max_turns_must_be_positive():
    with pytest.raises(ValueError):
        Conversation(FakeResponder(), max_turns=0)
