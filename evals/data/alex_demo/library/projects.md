# Projects of Alex Demo (fictional)

## Campus Events Portal
A web app where student clubs publish events and students register for them. Built with Python and FastAPI, with a PostgreSQL database.

The event and registration tables were designed in third normal form (3NF) to avoid update anomalies. A B+ tree index on the event date makes the "upcoming events" page fast, and registrations run inside a transaction so a seat is never booked twice.

The portal is deployed on AWS.

<!-- page -->

## Expense Splitter Bot
A Telegram bot that splits shared expenses between roommates. Written in Python with a SQLite database.

Each bot request is handled by a worker thread, and a lock prevents two threads from updating the same balance at once.
