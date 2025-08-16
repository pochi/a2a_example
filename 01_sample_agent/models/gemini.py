import base64
import json
import logging
import mimetypes
from typing import Any, AsyncGenerator, Optional, Protocol, Type, TypedDict, TypeVar, Union, cast, Generator

# import openai
# from openai.types.chat.parsed_chat_completion import ParsedChatCompletion
from google import genai
from google.genai.types import Content, Part

from pydantic import BaseModel
from typing_extensions import Unpack, override

from strands.types.content import ContentBlock, Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolResult, ToolSpec, ToolUse
from strands.models.model import Model

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class Client(Protocol):
    @property
    def chat(self) -> Any:
        ...

class GeminiModel(Model):
    client: Client

    class GeminiConfig(TypedDict, toatl=False):
        model_id: str
        params: Optional[dict[str, Any]]

    def __init__(self, client_args: Optional[dict[str, Any]] = None, **model_config: Unpack[GeminiConfig]) -> None:
        self.config = model_config
        logger.debug("config=<%s> | initialize", self.config)
        client_args = client_args or {}
        self.client = genai.Client(**client_args)

    @override
    def update_config(self, **model_config: Unpack[GeminiConfig]) -> None:
        self.config.update(model_config)

    @override
    def get_config(self) -> GeminiConfig:
        return cast(GeminiModel.GeminiConfig, self.config)

    @classmethod
    def format_request_message_content(cls, content: ContentBlock) -> dict[str, Any]:
        # :TODO: Implements document and image types
        return {"text": content["text"], "type": "text"}

    @classmethod
    def format_request_message_tool_call(cls, tool_use: ToolUse) -> dict[str, Any]:
        return {
            "function": {
                "arguments": json.dumps(tool_use['input']),
                "name": tool_use['name'],
            },
            "id": tool_use['toolUseId'],
            "type": 'function'
        }

    @classmethod
    def format_request_tool_message(cls, tool_result: ToolResult) -> dict[str, Any]:
        content = cast(
            list[ContentBlock],
            [
                {'text': json.dumps(content['json'])} if 'json' in content else content
                for content in tool_result['content']
            ],
        )

        return {
            'role': 'tool',
            'tool_call_id': tool_result['toolUseId'],
            'content': [cls.format_request_message_content(content) for content in contents],
        }

    @classmethod
    def format_request_messages(cls, messages: Messages, system_prompt: Optional[str] = None) -> list[dict[str, Any]]:
        formatted_messages: list[dict[str, Any]]
        formatted_messages = [{"role": "system", "content": system_prompt}] if system_prompt else []

        for message in messages:
            content = message["content"]
            formatted_contents = [
                cls.format_request_message_content(content)
                for content in contents
                if not any(block_type in content for block_type in ['toolResult', 'toolUse'])
            ]

            formatted_tool_calls = [
                cls.format_request_message_tool_call(content['toolUse']) for content  in contents if 'toolUse' in content
            ]

            formatted_tool_messages = [
                cls.format_request_tool_message(content['toolResult'])
                for content in contents
                if 'toolResult' in content
            ]

            formatted_message = {
                'role': message['role'],
                'content': formatted_contents,
                **({'tool_calls': formatted_tool_calls} if formatted_tool_calls or {}),
            }

            formatted_message.append(formatted_message)
            formatted_message.extend(formatted_tool_messages)

        return [message for message in formatted_messages if message['content'] or 'tool_calls' in message]

    def format_request(
        self, messages: Messages, tool_specs: Optional[list[ToolSpec]] = None, system_prompt: Optional[str] = None
    ) -> dict[str, Any]:
        return {
            'messages': self.format_request_messages(messages, system_prompt),
            'model': self.config['model_id'],
            'stream': True,
            'stream_options': {'included_usage': True},
            'tools': [
                {
                    'type': 'function',
                    'function': {
                        'name': tool_spec['name'],
                        'description': tool_spec['description'],
                        'parameters': tool_spec['inputSchema']['json'],
                    }
                }
                for tool_spec in tool_specs or []
            ],
            **cast(dict[str, Any], self.config.get('params', {})),
        }

    def format_chunk(self, event: dict[str, Any]) -> StreamEvent:
        match event['chunk_type']:
            case 'message_start':
                return {'messageStart': {'role': 'assistant'}}

            case 'content_start':
                if event['data_type'] == 'tool':
                    return {
                        'contentBlockStart': {
                            'start': {
                                'toolUse': {
                                    'name': event['data'].function.name,
                                    'toolUseId': event['data'].id
                                }
                            }
                        }
                    }

                return {'contentBlockStart': {'start': {}}}

            case 'content_delta':
                if event['data_type'] == 'tool':
                    return {
                        'contentBlockDelta': {'delta': {'toolUse':{
                            'input': event['data'].function.arguments or ''
                        }}}
                    }
                
                if event['data_type'] == 'reasoninig_content':
                    return {
                        'contentBlockDelta': {'delta': {'reasoningContent': {'text': event['data']}}}
                    }

                return {'contentBlockDelta': {'delta': {'text': event['data']}}}

            case 'content_stop':
                return {'contentBlockStop': {}}

            case 'message_stop':
                match event['data']:
                    case 'tool_calls':
                        return {'messageStop': {'stopReason': 'tool_use'}}
                    case 'length':
                        return {'messageStop': {'stopReason': 'max_tokens'}}
                    case _:
                        return {'messageStop': {'stopReason': 'end_turn'}}

            case 'metadata':
                return {
                    'metadata': {
                        'usage': {
                            'inputTokens': event['data'].prompt_tokens,
                            'outputTokens': event['data'].completion_tokens,
                            'totalTokens': event['data'].total_tokens,
                        },
                        'metrics': {
                            'latencyMs': 0,
                        }
                    }
                }

            case _:
                raise RuntimeError(f"chunk_type=<{event['chunk_type']} | unkwown_type")

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optinal[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[SteramEvent, None]:
        logger.debug('formatting request')
        request = self.format_request(messages, tool_specs, system_prompt)
        logger.debug("formatted request=<%s>", request)

        logger.debug('invoke model')
        response = await self.client.models.generate_content('gemini-2.0-flash', **request)

        


if __name__ == '__main__':
    print("hello, gemini")

