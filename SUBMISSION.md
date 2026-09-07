# Code Quality & Reflection

## Tool Descriptions
- **Memory Context Save**: Persists the user's name, preferences, and interaction history after each turn to allow for long-term recall across different sessions.
- **Memory Context Retrieve**: Queries specific memory namespaces (e.g., customer facts, preferences) before generating a response, ensuring the agent uses past context.
- **Knowledge Base Retrieve**: Connects to the Amazon Bedrock Knowledge Base (backed by OpenSearch and S3) to perform Retrieval-Augmented Generation (RAG) for accurate product and policy answers.
- **Browser Tools**: Navigates live websites to fetch real-time information, such as page titles or external content, directly within the agent's workflow.
- **Code Interpreter**: A secure sandbox environment to dynamically generate and execute Python code for precise tasks like calculating complex loyalty discounts.
- **get_orders (Order Tracker)**: An MCP-integrated Lambda tool via AgentCore Gateway that queries and returns shipping status, tracking numbers, and delivery estimates.
- **refund (Refund Processor)**: A Lambda tool connected via the Gateway to securely initiate and process customer product refund requests.

## Implementation Choice
Because the overall structure of the agent was already fully templated within the provided codebase, there isn't much to say regarding high-level architectural decisions. My implementation choices primarily revolved around efficiently following the scaffolding to wire the tools together without over-engineering the solution.

## Concrete Challenges

**1. API Gateway Integration Issue (Empty Responses)**
* **Problem & Investigation:** While setting up the API Gateway to route requests to the Lambda function, I found that requests made via `curl` and the API Gateway 'Test' tab executed successfully without errors, but valid data was not being fetched or returned. To diagnose, I mapped out our architecture (Bedrock Agent, Lambda, API Gateway, AgentCore Gateway) and consulted ChatGPT to trace the request payload drop.
* **Resolution:** The investigation revealed a quirk in how API Gateway passes payloads to Lambda functions. I had not enabled **Lambda Proxy Integration**. I went into the API Gateway settings and toggled "Lambda Proxy Integration" on, which correctly forwarded the raw request parameters and headers to the Lambda handler.
* **Verification:** Re-ran the exact same `curl` and 'Test' tab queries. The API correctly passed the payload to Lambda and returned the expected JSON records.

**2. Long-Term Memory Failing to Recall Context**
* **Problem & Investigation:** After deploying the setup, the agent was failing to recall context from previous messages in the session, despite no apparent configuration errors in the database or memory hooks. To isolate the issue, I systematically compared my current script line-by-line against a known working implementation from an earlier chapter's exercise.
* **Resolution:** The comparison revealed a missing argument in my agent initialization block. I had forgotten to pass the session state to the Agent instance. I updated the code to include `state={"actor_id": actor_id, "session_id": session_id}` inside the `Agent()` constructor.
* **Verification:** I ran a multi-turn conversation test. In the first prompt, I provided a specific detail, and in the follow-up prompt, I asked the agent to recall it. The agent successfully retrieved the context from memory, confirming the fix.

**3. Knowledge Base Authentication/Permission Errors**
* **Problem & Investigation:** When I queried the agent about specific "Platinum tier" loyalty rules, the LLM returned authentication/permission errors and hallucinated a response based on its base training data rather than the targeted knowledge base. Knowing that the AgentCore runtime calls the Knowledge Base directly, I immediately suspected an IAM access issue. 
* **Resolution:** I navigated to the AWS Console, located the IAM execution role associated with the AgentCore runtime, and attached a new policy. Specifically, I granted the `bedrock:RetrieveAndGenerate` (and `bedrock:Retrieve`) permissions, setting the resource to `*` to allow the runtime to access the configured knowledge base.
* **Verification:** I submitted the Platinum tier query again. The LLM successfully authenticated, searched the knowledge base, and accurately cited the Platinum tier rules directly from the source document, eliminating the fallback hallucination.

## Production Considerations
If I were to deploy this agent into a true production environment, my primary consideration would be adding robust monitoring and observability. I would want to integrate detailed traces and spans across the entire request lifecycle. Doing so would allow us to precisely pinpoint latency bottlenecks (such as a slow API Gateway or Lambda cold start) and granularly track the cost associated with each specific LLM generation and tool invocation.

---

## Test Scenarios

### Test 1 — Order Tracking
![Test 1](test-1.png)

### Test 2 — Refund Processing
![Test 2](test-2.png)

### Test 3 — Knowledge Base (RAG)
![Test 3](test-3.png)

### Test 4 — Memory (Long-Term)
![Test 4](test-4.png)

### Test 5 — Loyalty Discount Calculation
![Test 5](test-5.png)

### Test 6 — Browser Tool
![Test 6](test-6.png)
