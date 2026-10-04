# Database Management Systems: Notes

## Normalization
Normalization organises tables to reduce redundancy and update anomalies.

First Normal Form (1NF) requires atomic values. Second Normal Form (2NF) removes partial dependency on a composite key. Third Normal Form (3NF) removes transitive dependency of non-key attributes on the key. BCNF requires that every determinant is a candidate key.

<!-- page -->

## Transactions and ACID
A transaction is a logical unit of work. ACID stands for Atomicity, Consistency, Isolation and Durability.

Atomicity means all or nothing. Isolation means concurrent transactions do not see each other's partial results. Durability means committed changes survive crashes, usually through write-ahead logging.

<!-- page -->

## Indexing
An index speeds up lookups. A B+ tree index keeps all records in leaf nodes linked together, which makes range queries efficient. Hash indexes are fast for equality search but cannot answer range queries.
