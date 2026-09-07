"""
Customer Support AI Agent — Starter Code
==========================================
Your task is to complete this file by implementing all sections marked
with # TODO comments.

Reference the step-by-step solution files and INSTRUCTIONS.md for guidance.
Do NOT copy the solution directly — work through each section yourself.

Run locally (after filling in config values):
  uv run main.py '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'

Deploy to AgentCore:
  agentcore deploy

Invoke deployed agent:
  agentcore invoke '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'
"""

import argparse
import asyncio
import json
import logging
import os
import uuid
from typing import Dict

import boto3
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.tools.code_interpreter_client import code_session
from mcp.client.streamable_http import streamable_http_client
# ── Imports ───────────────────────────────────────────────────────────────────
# These imports are provided. Do not remove them.
from strands import Agent, tool, tools
from strands.hooks import (AfterInvocationEvent, HookProvider, HookRegistry,
                           MessageAddedEvent)
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from strands_tools.browser import AgentCoreBrowser

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("CSAI_Agent")

# ── TODO 1 — App Initialisation ───────────────────────────────────────────────
# Create a BedrockAgentCoreApp instance.
# This registers the ASGI server for AgentCore deployment.
# There must be exactly one instance per deployment.
#
# Hint: app = BedrockAgentCoreApp()

# TODO: Create the BedrockAgentCoreApp instance
app = BedrockAgentCoreApp()


# Suppress interactive tool-consent prompts (required in headless deployments).
os.environ["BYPASS_TOOL_CONSENT"] = "true"


# ── TODO 2 — Configuration ────────────────────────────────────────────────────
# Replace the placeholder strings with your actual AWS resource values.
# You collected these in Part 1 of the INSTRUCTIONS.
#
# GATEWAY_URL format: https://<alias>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp
# KB_ID       format: 10-character alphanumeric string from the KB console
# REGION:     your AWS region, e.g. "us-east-1"
# MEMORY_ID   format: shown in the AgentCore Memory console

GATEWAY_URL = "https://customersupportgateway-a7xv3nohhw.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"  # TODO: Replace with your Gateway URL
KB_ID = "USNSCD5SWV"  # TODO: Replace with your Knowledge Base ID
REGION = "us-east-1"  # TODO: Replace with your AWS region
MEMORY_ID = "CustomerSupportMemory-9w4egNHdlg"  # TODO: Replace with your Memory ID


# ── TODO 3 — Model and Clients ────────────────────────────────────────────────
# Create:
#   1. A BedrockModel using model_id "global.amazon.nova-2-lite-v1:0"
#   2. A MemoryClient with region_name=REGION
#   3. A boto3 client for the "bedrock-agent-runtime" service in REGION
#
# Hint: model = BedrockModel(model_id=model_id)

model_id = "global.amazon.nova-2-lite-v1:0"

# TODO: Create the BedrockModel instance
model = BedrockModel(model_id=model_id)

# TODO: Create the MemoryClient instance
memory_client = MemoryClient(region_name=REGION)

# TODO: Create the boto3 bedrock-agent-runtime client
_bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)


# ── TODO 4 — Namespace Helper ─────────────────────────────────────────────────
# Implement get_namespaces() to return a dict mapping strategy type to
# namespace template string.
#
# Steps:
#   1. Call mem_client.get_memory_strategies(memory_id) to get strategy list
#   2. Return a dict: { strategy["type"]: strategy["namespaces"][0] for each strategy }
#
# Example output:
#   { "SEMANTIC": "cs_agent/{actorId}/facts",
#     "USER_PREFERENCE": "cs_agent/{actorId}/preferences" }


def get_namespaces(mem_client: MemoryClient, memory_id: str) -> Dict:
    """Return a dict mapping strategy type → namespace template string."""
    # TODO: Implement this function
    strategies = mem_client.get_memory_strategies(memory_id)
    return {_strategy["type"]: _strategy["namespaces"][0] for _strategy in strategies}


# ── TODO 5 — Memory Hook ──────────────────────────────────────────────────────
# Implement MemoryHook, a HookProvider subclass that adds long-term memory.
#
# The class needs:
#   __init__(self, actor_id, session_id, memory_client, memory_id)
#     — store all four as instance attributes
#     — call get_namespaces() and store the result as self.namespaces
#
#   retrieve_customer_context(self, event: MessageAddedEvent)
#     — only runs for plain-text user messages (not tool results)
#     — for each strategy namespace, call memory_client.retrieve_memories(
#          memory_id, namespace (formatted with actorId), query, top_k=5)
#     — collect non-empty memory texts tagged with their strategy type
#     — if any memories found, prepend them to the user message as:
#          "Customer Context:\n<memories>\n\n<original_message>"
#
#   save_support_interaction(self, event: AfterInvocationEvent)
#     — walk the message list backwards to find the last plain-text user
#       query and the last assistant response
#     — call memory_client.create_event(memory_id, actor_id, session_id,
#          messages=[(customer_query, "USER"), (agent_response, "ASSISTANT")])
#
#   register_hooks(self, registry: HookRegistry)
#     — register retrieve_customer_context on MessageAddedEvent
#     — register save_support_interaction on AfterInvocationEvent


class MemoryHook(HookProvider):
    """Long-term memory hook for the customer support agent."""

    def __init__(
        self,
        actor_id: str,
        session_id: str,
        memory_client: MemoryClient,
        memory_id: str,
    ):
        # TODO: Store actor_id, session_id, memory_id, memory_client as attributes
        # TODO: Call get_namespaces() and store the result as self.namespaces
        self.actor_id = actor_id
        self.session_id = session_id
        self.memory_client = memory_client
        self.memory_id = memory_id
        self.namespaces = get_namespaces(self.memory_client, self.memory_id)
        logger.info("Namespaces loaded: %s", self.namespaces)

    def retrieve_customer_context(self, event: MessageAddedEvent):
        """Retrieve relevant memories and prepend them to the user message."""
        # TODO: Implement memory retrieval
        # Steps:
        #   1. Get the last message from event.agent.messages
        #   2. Check it is a user message and not a tool result
        #   3. Extract the user query text
        #   4. For each namespace in self.namespaces, call retrieve_memories()
        #   5. Collect non-empty memory texts with strategy type tags
        #   6. If any found, prepend them to the user message
        actor_id = event.agent.state.get("actor_id")
        if not actor_id:
            return
        messages = event.agent.messages

        if (
            not messages
            or messages[-1]["role"] != "user"
            or "toolResult" in messages[-1]["content"][0]
        ):
            return
        user_query = messages[-1]["content"][0]["text"]
        try:
            all_context = []
            for strategy_type, namespace in self.namespaces.items():
                resolved_namespace = namespace.format(actorId=actor_id)
                memories = self.memory_client.retrieve_memories(
                    memory_id=self.memory_id,
                    namespace=resolved_namespace,
                    query=user_query,
                    top_k=5,
                )
                for memory in memories:
                    if isinstance(memory, dict):
                        text = memory.get("content", {}).get("text", "").strip()
                        if text:
                            all_context.append(f"[{strategy_type}] {text}")

            if all_context:
                context_block = "\n".join(all_context)
                original_text = messages[-1]["content"][0]["text"]
                messages[-1]["content"][0][
                    "text"
                ] = f"Customer Context:\n{context_block}\n\n{original_text}"
                logger.info(
                    "Retrieved %d memory items for actor %s", len(all_context), actor_id
                )
        except Exception as exc:
            logger.error("Failed to retrieve customer context: %s", exc)

    def save_support_interaction(self, event: AfterInvocationEvent):
        """Save the completed turn to memory after the agent responds."""
        # TODO: Implement memory saving
        # Steps:
        #   1. Get messages from event.agent.messages
        #   2. Walk backwards to find the last user query (plain text)
        #      and the last assistant response
        #   3. Call memory_client.create_event() with both messages
        actor_id = event.agent.state.get("actor_id")
        session_id = event.agent.state.get("session_id")
        if not actor_id or not session_id:
            return

        try:
            messages = event.agent.messages
            user_text = agent_text = None

            for msg in reversed(messages):
                if msg["role"] == "assistant" and not agent_text:
                    content = msg["content"]
                    if isinstance(content, list):
                        agent_text = content[0].get("text", "")
                    else:
                        agent_text = str(content)
                elif (
                    msg["role"] == "user"
                    and not user_text
                    and "toolResult" not in msg["content"][0]
                ):
                    user_text = msg["content"][0]["text"]
                    break

            if user_text and agent_text:
                self.memory_client.create_event(
                    memory_id=self.memory_id,
                    actor_id=actor_id,
                    session_id=session_id,
                    messages=[
                        (user_text, "USER"),
                        (agent_text, "ASSISTANT"),
                    ],
                )
                logger.info("Saved interaction to memory for actor %s", actor_id)

        except Exception as exc:
            logger.error("Failed to save interaction: %s", exc)

    def register_hooks(self, registry: HookRegistry) -> None:  # type: ignore
        """Register both memory callbacks."""
        # TODO: Register retrieve_customer_context on MessageAddedEvent
        # TODO: Register save_support_interaction on AfterInvocationEvent
        registry.add_callback(MessageAddedEvent, self.retrieve_customer_context)
        registry.add_callback(AfterInvocationEvent, self.save_support_interaction)


# ── TODO 6 — Knowledge Base Tool ─────────────────────────────────────────────
# Implement search_knowledge_base(query) using the @tool decorator.
#
# Steps:
#   1. Guard: if KB_ID is empty return "Knowledge base not configured."
#   2. Call _bedrock_runtime.retrieve(
#          knowledgeBaseId=KB_ID,
#          retrievalQuery={"text": query}
#      )
#   3. Extract resp["retrievalResults"]; return a message if empty
#   4. Join the text chunks with "\n---\n" and return the result
#
# The docstring is the tool description — the model uses it to decide when
# to call this tool, so keep it clear and accurate.


@tool
def search_knowledge_base(query: str) -> str:
    """
    Search the Amazon product catalog and support knowledge base.
    Use this for product specifications, return policies, warranty
    information, loyalty program details, and order status definitions.

    Args:
        query: The question or topic to search for

    Returns:
        Relevant information retrieved from the knowledge base
    """
    # TODO: Implement the Knowledge Base search
    if not KB_ID:
        return "Knowledge base not configured"

    resp = _bedrock_runtime.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": query},
    )
    results = resp.get("retrievalResults", [])
    if not results:
        return f"No information found for: {query}"

    chunks = [r["content"]["text"] for r in results]
    return "\n---\n".join(chunks)


# ── TODO 7 — Loyalty Discount Tool (Code Interpreter) ────────────────────────
# Implement calculate_loyalty_discount() using the @tool decorator.
#
# The tool must:
#   1. Build a self-contained Python code string that:
#        • Defines earn_rates: {"standard": 1, "device": 2, "fresh": 5}
#        • Defines tier_rates: {"Silver": 0.00, "Gold": 0.10, "Platinum": 0.15}
#        • Calculates points_redeemed (floor to nearest 500, cap at 50% of order)
#        • Calculates tier_discount (applied to subtotal after points)
#        • Calculates final_total, total_savings, points_earned, remaining_points
#        • Prints a JSON result dict
#   2. Execute the code with code_session(REGION).invoke("executeCode", {...})
#      using language="python" and clearContext=True
#   3. Return the first result event as a JSON string
#   4. Include a fallback that computes only the tier discount if the
#      Code Interpreter is unavailable


@tool
def calculate_loyalty_discount(
    loyalty_points: int,
    tier: str,
    order_total: float,
    product_category: str = "standard",
) -> str:
    """
    Calculate the loyalty discount for a customer order using the
    AgentCore Code Interpreter. Runs exact arithmetic in a secure sandbox.

    Args:
        loyalty_points:   Customer's current points balance
        tier:             Customer tier — Silver, Gold, or Platinum
        order_total:      Order total in USD
        product_category: standard, device, or fresh

    Returns:
        Full discount breakdown and final price
    """
    # Build a self-contained Python script that computes the full discount breakdown
    code = f"""
import math, json

loyalty_points   = {loyalty_points}
tier             = "{tier}"
order_total      = {order_total}
product_category = "{product_category}"

# Points-earned rates per dollar spent
earn_rates = {{"standard": 1, "device": 2, "fresh": 5}}

# Tier discount percentages applied to the subtotal after points redemption
tier_rates = {{"Silver": 0.00, "Gold": 0.10, "Platinum": 0.15}}

# --- Points redemption ---
# Redeem in multiples of 500 pts (each 500 pts = $5 off); cap at 50 % of order
points_per_block = 500
discount_per_block = 5.0
max_points_value = order_total * 0.50

redeemable_blocks = math.floor(loyalty_points / points_per_block)
max_blocks        = math.floor(max_points_value / discount_per_block)
blocks_used       = min(redeemable_blocks, max_blocks)

points_redeemed   = blocks_used * points_per_block
points_discount   = blocks_used * discount_per_block

subtotal_after_points = order_total - points_discount

# --- Tier discount ---
tier_pct      = tier_rates.get(tier, 0.00)
tier_discount = subtotal_after_points * tier_pct

final_total    = subtotal_after_points - tier_discount
total_savings  = order_total - final_total

# --- Points earned on this purchase ---
earn_rate      = earn_rates.get(product_category, 1)
points_earned  = int(final_total * earn_rate)
remaining_pts  = loyalty_points - points_redeemed + points_earned

result = {{
    "order_total":        round(order_total, 2),
    "points_redeemed":    points_redeemed,
    "points_discount":    round(points_discount, 2),
    "tier":               tier,
    "tier_discount_pct":  tier_pct,
    "tier_discount":      round(tier_discount, 2),
    "final_total":        round(final_total, 2),
    "total_savings":      round(total_savings, 2),
    "points_earned":      points_earned,
    "remaining_points":   remaining_pts,
}}

print(json.dumps(result))
"""

    try:
        # Execute the code in an isolated AgentCore sandbox
        with code_session(REGION) as code_client:
            response = code_client.invoke(
                "executeCode",
                {
                    "code": code,
                    "language": "python",
                    "clearContext": True,  # fresh sandbox every call — no state leaks
                },
            )

        for event in response["stream"]:
            return json.dumps(event["result"])

    except Exception as e:
        # Fallback: compute only the tier discount if Code Interpreter is unavailable
        logger.warning("Code Interpreter unavailable, using fallback: %s", e)
        tier_rates = {"Silver": 0.00, "Gold": 0.10, "Platinum": 0.15}
        tier_pct = tier_rates.get(tier, 0.00)
        tier_discount = order_total * tier_pct
        final_total = order_total - tier_discount
        return json.dumps(
            {
                "order_total": round(order_total, 2),
                "tier": tier,
                "tier_discount_pct": tier_pct,
                "tier_discount": round(tier_discount, 2),
                "final_total": round(final_total, 2),
                "points_redeemed": 0,
                "remaining_points": loyalty_points,
                "note": "Fallback calculation — points redemption skipped",
                "error": str(e),
            }
        )


# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are SupportBot, the AI customer support agent for Amazon.

You have PERSISTENT MEMORY: you remember each customer's preferences, past orders,
and support history across multiple conversations.

MEMORY-AWARE BEHAVIOUR
- When a "Customer Context" block appears at the start of the user's message,
  it contains facts retrieved from past conversations.
- Use this context to personalise your responses naturally — reference it as
  "Based on your previous order..." or "I see you prefer...".
- Never ask the customer to repeat information they have already shared.

KNOWLEDGE BASE
You have access to a knowledge base containing:
- Amazon product catalogue, specifications, and availability
- Return and refund policies, warranty terms, and order status definitions
- Loyalty programme rules, tier benefits, and points redemption details

ALWAYS use the search_knowledge_base tool before answering questions about:
- Product specifications, compatibility, or pricing
- Return / refund / warranty policies and procedures
- Loyalty programme rules, tier benefits, or points redemption
- Order status definitions or shipping timelines

Base policy answers on retrieved content — quote exact figures and cite the
relevant policy section. If the knowledge base does not cover the question,
say so honestly rather than guessing.

LOYALTY DISCOUNT CALCULATIONS
You have access to the calculate_loyalty_discount tool, which runs exact
arithmetic inside a secure, isolated Python sandbox via the AgentCore Code
Interpreter.

USE calculate_loyalty_discount WHENEVER a customer asks about:
- How much a specific order will cost after applying their loyalty points
- What their tier discount saves them
- How many points they will earn or have remaining after a purchase

Never estimate or guess discount amounts yourself — always delegate to the tool
and present the result clearly with a brief explanation.

LIVE BROWSER
You have access to a live web browser. Use it to look up real-time product
information, order tracking pages, or any public web resource the customer
needs — for example, the Amazon help centre or a carrier's tracking portal.

When a customer asks you to check a live page, follow these exact steps:
1. Call browser with action type "init_session":
   - session_name MUST use ONLY lowercase letters (a-z), digits (0-9), and hyphens (-).
     NO underscores, NO spaces, NO uppercase. Minimum 10 characters, maximum 36.
     Good examples: "page-check-01", "udacity-lookup", "web-session-01"
     Bad examples: "title_check", "titleCheck", "check" (too short)
2. Call browser with action type "navigate" using the same session_name and the target URL
3. Call browser with action type "evaluate" using script "document.title" to get the page title,
   or use "get_text" with an appropriate selector to read page content
4. Call browser with action type "close" using the same session_name when done
5. Always tell the customer where the information came from (the URL you visited)

Use the browser only when the knowledge base does not contain the answer and
a live lookup would genuinely help the customer.

TONE & STYLE
Be professional, empathetic, and solution-focused. Acknowledge frustration when
a customer is upset. Keep responses concise but complete — avoid bullet-point
walls unless genuinely helpful. Always end with a clear next step or ask if
there is anything else you can help with.
"""


# ── TODO 8 — Agent Entrypoint ─────────────────────────────────────────────────
# Implement the invoke() function decorated with @app.entrypoint.
#
# Steps:
#   1. Extract user_input, actor_id, and session_id from the payload
#      (generate a UUID if session_id is missing)
#   2. Instantiate MemoryHook for this actor/session
#   3. Instantiate AgentCoreBrowser(region=REGION)
#   4. Build the tools list: [search_knowledge_base, calculate_loyalty_discount,
#                              agent_core_browser.browser]
#   5. Connect to the Gateway via MCPClient, load gateway_tools, extend tools list
#   6. Create and invoke the Agent with all tools, hooks, and system_prompt
#   7. Return the text from the first content block of the response
#   8. Handle exceptions gracefully


@app.entrypoint
async def invoke(payload, context=None):
    """
    Main handler called by AgentCore for every incoming request.

    Expected payload keys:
      prompt      (str, required) — the customer's message
      customer_id (str, optional) — unique customer identifier
      session_id  (str, optional) — session identifier; generated if absent
    """
    # TODO: Implement the agent invocation
    user_message = payload.get("prompt", payload.get("message", "Hello"))
    session_id = payload.get("session_id", str(uuid.uuid4()))
    actor_id = payload.get("customer_id", payload.get("actor_id", "ai-support-user"))

    logger.info(
        "Session %s | Actor %s | User: %s", session_id, actor_id, user_message[:80]
    )

    memory_hook = MemoryHook(
        memory_client=memory_client,
        memory_id=MEMORY_ID,
        actor_id=actor_id,
        session_id=session_id,
    )

    browser = AgentCoreBrowser(region=REGION, session_timeout=600)
    local_tools = [search_knowledge_base, calculate_loyalty_discount, browser.browser]

    client = MCPClient(lambda: streamable_http_client(url=GATEWAY_URL))

    with client:
        gateway_tools = client.list_tools_sync()
        logger.info("Discovered %d tools from Gateway", len(gateway_tools))
        all_tools = local_tools + gateway_tools
        agent = Agent(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            tools=all_tools,
            state={"actor_id": actor_id, "session_id": session_id},
            hooks=[memory_hook],
        )

        response = agent(user_message)
        return response


# ── CLI entry point (do not modify) ──────────────────────────────────────────
def main():
    """Run one invocation from the command line for local testing."""
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=str)
    args = parser.parse_args()
    response = asyncio.run(invoke(json.loads(args.payload)))
    print(response)


if __name__ == "__main__":
    app.run()
    # Uncomment the line below and comment app.run() for local CLI testing:
    # main()
