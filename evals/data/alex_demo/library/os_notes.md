# Operating Systems: Lecture Notes (Unit 2 to Unit 4)

## Processes and threads
A process is a program in execution. It has its own address space, open files and a process control block (PCB) that stores its state, program counter and registers.

A thread is a lightweight unit of execution inside a process. Threads of the same process share code, data and open files, but each thread has its own stack and registers.

<!-- page -->

## CPU scheduling
The CPU scheduler picks which ready process runs next. First-Come First-Served (FCFS) is simple but suffers from the convoy effect.

Shortest Job First (SJF) gives the minimum average waiting time, but it needs the length of the next CPU burst in advance.

Round Robin gives each process a fixed time quantum. If the quantum is too large it behaves like FCFS; if it is too small, context-switch overhead dominates.

<!-- page -->

## Deadlock
A deadlock is a situation where a set of processes are blocked forever, each waiting for a resource held by another process in the set.

Deadlock can occur only if four Coffman conditions hold at the same time: mutual exclusion, hold and wait, no preemption, and circular wait.

Deadlock prevention breaks at least one of the four conditions. Deadlock avoidance uses the Banker's algorithm to keep the system in a safe state. Detection and recovery lets deadlock happen and then aborts a process or preempts resources.

<!-- page -->

## Memory management: paging
Paging divides physical memory into fixed-size frames and logical memory into pages of the same size. A page table maps each page number to a frame number.

Paging removes external fragmentation, but it can cause internal fragmentation in the last page of a process.

A Translation Lookaside Buffer (TLB) is a small fast cache of page-table entries that speeds up address translation.

## Segmentation
Segmentation divides a program into variable-sized logical segments such as code, stack and heap. Each segment has a base and a limit. Segmentation matches the programmer's view of memory but suffers from external fragmentation.
