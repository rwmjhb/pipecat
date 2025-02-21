#
# Copyright (c) 2024, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

from typing import Union

from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesFrame,
    LLMResponseEndFrame,
    LLMResponseStartFrame,
    TextFrame)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from loguru import logger

try:
    from langchain_core.messages import AIMessageChunk
    from langchain_core.runnables import Runnable
except ModuleNotFoundError as e:
    logger.exception(
        "In order to use Langchain, you need to `pip install pipecat-ai[langchain]`. "
    )
    raise Exception(f"Missing module: {e}")


class LangchainProcessor(FrameProcessor):
    def __init__(self, chain: Runnable, transcript_key: str = "input"):
        super().__init__()
        self._chain = chain
        self._transcript_key = transcript_key
        self._participant_id: str | None = None

    def set_participant_id(self, participant_id: str):
        self._participant_id = participant_id

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, LLMMessagesFrame):
            # Messages are accumulated by the `LLMUserResponseAggregator` in a list of messages.
            # The last one by the human is the one we want to send to the LLM.
            logger.debug(f"Got transcription frame {frame}")
            text: str = frame.messages[-1]["content"]

            await self._ainvoke(text.strip())
        else:
            await self.push_frame(frame, direction)

    @staticmethod
    def __get_token_value(text: Union[str, AIMessageChunk]) -> str:
        match text:
            case str():
                return text
            case AIMessageChunk():
                return text.content
            case _:
                return ""

    async def _ainvoke(self, text: str):
        logger.debug(f"Invoking chain with {text}")
        await self.push_frame(LLMFullResponseStartFrame())
        try:
            async for token in self._chain.astream(
                {self._transcript_key: text},
                config={"configurable": {"session_id": self._participant_id}},
            ):
                await self.push_frame(LLMResponseStartFrame())
                await self.push_frame(TextFrame(self.__get_token_value(token)))
                await self.push_frame(LLMResponseEndFrame())
        except GeneratorExit:
            logger.warning("Generator was closed prematurely")
        except Exception as e:
            logger.error(f"An unknown error occurred: {e}")
        await self.push_frame(LLMFullResponseEndFrame())
