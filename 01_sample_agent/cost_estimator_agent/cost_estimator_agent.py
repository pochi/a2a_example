import logging
import traceback
import boto3
from contextlib import contextmanager
from typing import Generator, AsyncGenerator
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from strands.handlers.callback_handler import null_callback_handler
from mcp import stdio_client, StdioServerParameters
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

from cost_estimator_agent.config import(
    SYSTEM_PROMPT,
    COST_ESTIMATION_PROMPT,
    DEFAULT_MODEL,
    DEFAULT_REGION,
    LOG_FORMAT
)

logging.basicConfig(
    level=logging.ERROR, # level can change ERROR/DEBUG if you want to decrease/increase information
    format=LOG_FORMAT,
    handlers=[logging.StreamHandler()]
)

logging.getLogger('strands').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

class AWSCostEstimatorAgent:
    def __init__(self, region:str=DEFAULT_REGION):
        self.region = region
        self.code_interpreter = None
        logger.info(f"Initializing AWS Cost Estimation Agent in region: {region}")

    def _setup_code_interpreter(self) -> None:
        try:
            logger.info("Setting up AgentCore code interpreter")
            self.code_interpreter = CodeInterpreter(self.region)
            self.code_interpreter.start()
            logger.info("👍 AgentCore Codeintepreter session started")
        except Exception as e:
            logger.exception(f"✖️ Failed to setup code interpreter: {e}")
            raise e

    def _get_aws_credentials(self) -> dict:
        try:
            logger.info("💪 Getting current AWS credentials")
            session = boto3.Session()
            credentials = session.get_credentials()

            if credentials is None:
                raise Exception("✖️ No AWS credentials found")

            sts_client = boto3.client('sts', region_name=self.region)
            identity = sts_client.get_caller_identity()
            logger.info(f"💁‍♂️ Using AWS identity: {identity.get('Arn', 'Unknown')}")

            # ❓ what is frozen_credentials?
            frozen_credentials = credentials.get_frozen_credentials()
            credential_dict = {
                "AWS_ACCESS_KEY_ID": frozen_credentials.access_key,
                "AWS_SECRET_ACCESS_KEY": frozen_credentials.secret_key,
                "AWS_REGION": self.region
            }

            # ❓ this dict will not be used
            if frozen_credentials.token:
                credential_dict["AWS_SESSION_TOKEN"] = frozen_credentials.token

            return credential_dict
        except Exception as e:
            logger.exception(f"❌ Failed to get AWS credentials: {e}")
            raise

    def _setup_aws_pricing_client(self) -> MCPClient:
        try:
            logger.info("🤖 Setting up AWS Pricing MCP Client...")
            aws_credentials = self._get_aws_credentials()

            environemnt_variables = {
                "FASTMCP_LOG_LEVEL": "ERROR",
                **aws_credentials
            }

            aws_pricing_client = MCPClient(
                lambda: stdio_client(StdioServerParameters(
                    command = "uvx",
                    args=["awslabs.aws-pricing-mcp-server@latest"],
                    env=environemnt_variables
                ))
            )
            logger.info("💁‍♂️ AWS Pricing MCP Client setup successfully")
            return aws_pricing_client
        except Exception as e:
            logger.info(f"✖️ Failed to setup AWS Pricinig MCP Client: {e}")
            raise e

    @tool
    def execute_cost_calculation(self, calculation_code: str, description: str="") -> str:
        if not self.code_interpreter:
            return "✖️ Code interpreter not initialized"
        
        try:
            logger.info(f"🌟 Executing calculation: {description}")
            logger.debug(f"Code to execute: \n{calculation_code}")

            response = self.code_interpreter.invoke("executeCode", {
                "language": "python",
                "code": calculation_code
            })

            results = []
            for event in results.get("stream", []):
                if "result" in event:
                    result = event["result"]
                    if "content" in result:
                        for content_item in result["content"]:
                            if content_item.get("type") == "text":
                                results.append(content_type["text"])

            result_text = "\n".join(results)
            logger.info(f"✅ Calculation completed successfully: {result_text}")

            return result_text
        
        except Exception as e:
            logger.exception(f"❌ Calculation failed: {e}")

    @contextmanager
    def _estimation_agent(self) -> Generator[Agent, None, None]:
        try:
            logger.info("🚀Initializing AWS Cost Estimation Agent...")
            self._setup_code_interpreter()
            aws_pricing_client = self._setup_aws_pricing_client()

            with aws_pricing_client:
                pricing_tools = aws_pricing_client.list_tools_sync()
                logger.info(f"Found {len(pricing_tools)} AWS pricing tools")
                all_tools = [self.execute_cost_calculation] + pricing_tools
                model = BedrockModel(
                    model_id = DEFAULT_MODEL,
                    region_name = self.region,
                    temprature=0.0, # this is recommended by [aws guide](https://docs.aws.amazon.com/nova/latest/userguide/prompting-tool-troubleshooting.html)
                    streaming=False
                )

                agent = Agent(
                    model=model,
                    tools=all_tools,
                    system_prompt=SYSTEM_PROMPT
                )

                yield agent
        except Exception as e:
            logger.exception(f"✖️ Component setup failed: {e}")
            raise e
        finally:
            self.cleanup()
    
    def estimate_costs(self, architecture_description: str) -> str:
        logger.info("💹 Starting cost estimation...")
        logger.info(f"Architecture: {architecture_description}")

        try:
            with self._estimation_agent() as agent:
                prompt = COST_ESTIMATION_PROMPT.format(
                    architecture_description=architecture_description
                )

                result = agent(prompt)

                logger.info("✅ Cost estimation completed")
                if result.message and result.message.get("content"):
                    text_parts = []
                    for content_block in result.message["content"]:
                        if isinstance(content_block, dict) and "text" in content_block:
                            text_parts.append(content_block["text"])

                    return "".join(text_parts) if text_parts else "No text content found."
                else:
                    return "No estimation result."
        except Exception as e:
            logger.exception(f"✖️ Cost estimation failed: {e}")
            error_details = traceback.format_exc()
            return f"🆖 Cost estimation failed: {e}\n\n Stacktrace:\n{error_details}"

    def cleanup(self) -> None:
        logger.info("🧹Cleaning up resources..")
        if self.code_interpreter:
            try:
                self.code_interpreter.stop()
                logger.info("✅ Code interpreter session stopped")
            except Exception as e:
                logger.warining(f"⚠️ Error stopping Code interpreter: {e}")
            finally:
                self.code_interpreter = None

