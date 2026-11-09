"""Small Operating Systems sample so the app can be tried without uploading files."""

SYLLABUS = [{"label": "syllabus", "text": (
    "Operating Systems: Course Syllabus.\n"
    "Unit 1: Processes and Threads. Process states, process control block (PCB), context switching, threads versus processes.\n"
    "Unit 2: CPU Scheduling. FCFS, SJF, Round Robin, priority scheduling, turnaround time and waiting time.\n"
    "Unit 3: Synchronization and Deadlocks. Race conditions, critical section, mutex, semaphores, deadlock conditions, avoidance and prevention.\n"
    "Unit 4: Memory Management. Paging, segmentation, virtual memory, page faults, page replacement algorithms, thrashing.\n"
    "Unit 5: File Systems. File allocation methods, inodes, directories, disk scheduling.")}]

NOTES = [
    {"label": "Processes and Threads", "text": (
        "A process is a program in execution with its own address space. The operating system tracks each process in a Process Control Block (PCB) holding the process state, program counter, CPU registers and memory information. Process states are new, ready, running, waiting and terminated. A context switch saves the state of the running process into its PCB and loads the state of the next process; it is pure overhead because no useful work is done during it. Threads are lightweight units of execution inside a process; threads of one process share code, data and open files but each has its own stack and registers, so creating and switching threads is cheaper than for processes.")},
    {"label": "CPU Scheduling", "text": (
        "The scheduler picks which ready process runs next. First-Come First-Served (FCFS) runs processes in arrival order and suffers from the convoy effect when a long job arrives first. Shortest Job First (SJF) gives the minimum average waiting time but needs the next CPU burst length, which must be predicted, and long jobs can starve. Round Robin gives each process a fixed time quantum, then preempts it; a very large quantum makes it behave like FCFS while a very small quantum wastes time on context switches. Turnaround time is completion time minus arrival time and waiting time is turnaround time minus burst time. Priority scheduling can starve low-priority processes, which is solved by aging, gradually raising the priority of waiting processes.")},
    {"label": "Synchronization and Deadlocks", "text": (
        "A race condition occurs when the result depends on the order in which processes access shared data. The critical section is the code that accesses shared data and must be executed by one process at a time. A mutex lock provides mutual exclusion; a counting semaphore uses wait (P) and signal (V) operations on an integer value to control access to a limited number of resources. A deadlock requires four conditions at once: mutual exclusion, hold and wait, no preemption and circular wait. Deadlock avoidance with the Banker's algorithm grants a request only if the system stays in a safe state, while prevention works by breaking one of the four conditions, for example by imposing a global ordering on resources to stop circular wait.")},
    {"label": "Memory Management", "text": (
        "Paging divides physical memory into fixed-size frames and logical memory into pages of the same size, and a page table maps each page to a frame; this removes external fragmentation but can leave internal fragmentation in the last page. Segmentation divides a program into variable-size logical units such as code, stack and heap. Virtual memory lets a program run when only part of it is in RAM; a page fault happens when a referenced page is not in memory and the OS must load it from disk. Page replacement algorithms choose the victim page: FIFO is simple but can show Belady's anomaly, where more frames cause more faults, while the optimal algorithm replaces the page that will not be used for the longest time and LRU approximates it using past usage. Thrashing occurs when a process spends more time paging than executing, which happens when it does not have enough frames.")},
    {"label": "File Systems", "text": (
        "Contiguous allocation stores a file in consecutive blocks, giving fast access but external fragmentation. Linked allocation stores each block with a pointer to the next, which suits sequential access but makes random access slow. Indexed allocation keeps all block pointers of a file in an index block, supporting direct access. In Unix file systems an inode stores file metadata and block pointers, but not the file name; names are stored in directory entries. Disk scheduling algorithms reduce seek time: SSTF serves the nearest request, SCAN moves the head in one direction like an elevator and then reverses, and C-SCAN returns to the start after reaching one end to give more uniform waiting times.")},
]

PAST = [{"label": "paper", "text": (
    "Past Paper 2025, Operating Systems. "
    "Q1. Differentiate between a process and a thread. (5 marks) "
    "Q2. Calculate the average waiting time for processes P1, P2, P3 with burst times 24, 3, 3 under FCFS and under Round Robin with quantum 4. (8 marks) "
    "Q3. Explain the four necessary conditions for deadlock and how the Banker's algorithm avoids it. (8 marks) "
    "Q4. What is a page fault? Compare FIFO and LRU page replacement. (6 marks) "
    "Q5. Explain thrashing and one way to prevent it. (4 marks) "
    "Q6. Compare contiguous, linked and indexed file allocation. (6 marks) "
    "Q7. Describe the Round Robin scheduling algorithm and the effect of the time quantum. (5 marks)")}]
