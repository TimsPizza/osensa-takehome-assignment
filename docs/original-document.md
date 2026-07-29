OSENSA Restaurant Full Stack Assignment
Summary
Write a web app to simulate ordering food by customers in a restaurant.
User Interface
This web app has a simple one page interface.
There are fixed number of tables in this restaurant (you can choose a number like 4). Tables should be
numbered.
There will be an ORDER button for each table. The customer can click on ORDER button which
should open a pop-up to take in the name of the food the customer wants to order. The name of the food
is free text.
After the order is submitted, it will take a random amount of time for it get ready. When the ordered
food is ready it should show up on the table of the customer that ordered it.
Customers can order at the same time.
Food should show up as soon as it is ready.
The UI can be as basic and simple as it can be. No styling is required.

Architecture
Design an event driven web app.
Frontend generates ORDER events that the backend would receive and process.
Backend generates FOOD events that the frontend would receive and process.
Keeping application state in memory is acceptable; it does not need to survive a restart.

Communication
Only use MQTT over WebSockets as the communication protocol between the frontend and the
backend. Do not use RESTFul API.

Frontend
Use Svelte with TypeScript to implement the frontend. You can use any lib you need.

Backend
Use Python with the asyncio module to implement the backend. You can use any lib you need.

Requirements
• The code should be production ready. Given the time limit we don't expect every item below to
be fully polished - show us that you understand what production ready means and note any
trade-offs you made:
◦ Well tested
◦ Handles edge cases
◦ Takes care of errors
◦ Provides logging
◦ Is secure
◦ Properly documented

Deliverable

Email project's Git URL and demo link to fpanahi@osensa.com.

Include a short README that covers:

• How to run the app.

• Key design decisions and the trade-offs you made.

• What you would improve or add with more time.

You may use AI tools to help you, but be prepared to explain and defend every line of your submission
in a follow-up discussion.

Deadline

We expect this to take roughly 4 to 8 hours of focused work. This assignment is due 72 hours after it
has been sent to you by email. Contact fpanahi@osensa.com  in case you need more time to finish the
assignment or if you have any questions regarding the assignment.
