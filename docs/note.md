1. okay, I need to make a web application with svelte/ts and python as backend. 
2. No rest api. And MQTT over WS is explicitly mentioned, so aiomqtt is a good choice. 
3. zod and pydantic needed for schema validation.
4. backend test
5. better keep track of llm usage
6. repo initialized and bootstraped.
7. ok im gonna use QoS 1 for deduplication as QoS 2 is overcomplicated, idempotence needed to be implemented.
8. 
8. will use docker compose for easier deployment (VPS), now work on MVP, including caddy, Mosquitto, python backend remains manually-run now for easy code update. But the MVP will use WS only for validation. Will test capability of WSS on OCI VPS later.
9. I'm going to smoke test dockerization. --ok for 127.0.0.1
10. ok, designing a FSM is helpful for this system, as processing idempotence can be implicit somehow.
11. ok FSM has been implemented and tested, now bridge it into business logic
12. FSMed processing logic tested. Regression test ok. 
13. Idempotence registry implemented, enforced by 'order_id'. Regression ok


14. oh wait I found an issue: now the code uses 'asyncio.Semaphore(max_concurrent_orders)' for concurrency control, but when new order incomes and the system reaches its maximum concurrency, the new orders will be piled or discarded.. also the 'queued' state is not used in this situation. I'm going to refactor the system using producer-consumer queue and worker pool instead.
15. okay the producer-consumers & worker pool refactor is done. Regression test ok
16. I think I should start working on frontend now, it better has 4 tables as what the requirement says, and sepaarated controls&displays


17. oh maybe I should add intuitive test buttons on the webui
18. okay, now I need to use mqtt retain flag and snapshot to restore webui state after refresh, therefore another snapshot endpoint is needed. 
19. do I need to throttle the rate of order update event -> frontend? no no that's overkilling for this scenario
20. hmm, maybe I need a stress test panel


21. now test for pub net deployment, will be vercel + OCI VPS.
