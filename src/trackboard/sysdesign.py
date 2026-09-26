"""System design curriculum: original notes, three levels, each with an animated scene.
Static content in code — no database, no writes, no load. Topic order follows the
conventional interview syllabus; the explanations are Athena's own."""
from __future__ import annotations

LEVELS = [("basics", "Basics"), ("core", "Core building blocks"), ("advanced", "Case studies")]

TOPICS: list[dict] = [
    {
        "slug": "scaling-from-one-server", "level": "basics", "title": "From one server to millions of users", "scene": "fanout",
        "summary": "Every large system started as one box. Growth is a sequence of splits: separate the database, put a load balancer in front, add replicas, cache what's hot, push static files to a CDN, then shard.",
        "ideas": [
            "Vertical first (bigger machine), horizontal when a single box becomes a single point of failure.",
            "Stateless web tier: any request can hit any server, so servers become disposable.",
            "Read replicas absorb reads; writes still go to one primary until you shard.",
            "Cache the hot 20% of data that serves 80% of reads; cache aside is the default pattern.",
            "CDN for static assets; users hit an edge near them, your origin sees a fraction of traffic.",
        ],
        "interview": ["Ask for read/write ratio before choosing replicas vs sharding.", "Name the single points of failure at each step and how you remove them.", "Say what breaks first at 10× traffic."],
        "reading": [("Scalability for dummies", "https://www.lecloud.net/tagged/scalability"), ("The Twelve-Factor App", "https://12factor.net/")],
    },
    {
        "slug": "estimation", "level": "basics", "title": "Back-of-the-envelope estimation", "scene": "numbers",
        "summary": "Interviewers want to see you size the problem in a minute: QPS, storage, bandwidth. Memorise a few latency numbers and powers of two, then reason in round figures.",
        "ideas": [
            "Daily active users × actions per day ÷ 86,400 ≈ average QPS; peak is 2–5× that.",
            "Storage per year = objects per day × bytes per object × 365; keep three copies.",
            "Memory read ~100 ns, SSD ~100 µs, disk ~10 ms, same-region network ~0.5 ms, cross-continent ~150 ms.",
            "2^10 ≈ 1 thousand, 2^20 ≈ 1 million, 2^30 ≈ 1 billion; 1 million bytes = 1 MB.",
            "State your assumptions out loud; the arithmetic matters less than the reasoning.",
        ],
        "interview": ["Round aggressively: 86,400 seconds a day becomes 100,000.", "Convert to a unit the interviewer cares about (servers, dollars, disks).", "Check the answer is plausible: 10 million QPS for a todo app is a sign you slipped a decimal."],
        "reading": [("Latency numbers every programmer should know", "https://gist.github.com/jboner/2841832")],
    },
    {
        "slug": "interview-framework", "level": "basics", "title": "A framework for the interview itself", "scene": "steps",
        "summary": "Forty-five minutes, four phases. Most candidates fail by skipping the first one and designing something the interviewer never asked for.",
        "ideas": [
            "1. Clarify scope (5 min): who uses it, which features, what scale, what's out of scope.",
            "2. High-level design (15 min): boxes and arrows, the request path, the data model. Get agreement before going deep.",
            "3. Deep dive (20 min): pick the two hardest components together with the interviewer and design them properly.",
            "4. Wrap up (5 min): failure modes, bottlenecks, what you'd do with more time.",
            "Drive the conversation; silence while thinking is fine, silence while stuck is not — say what you're weighing.",
        ],
        "interview": ["Write the requirements on the board and refer back to them.", "Trade-offs beat features: every choice should have a 'because'.", "Never say 'we could use Kafka' without saying what problem it solves here."],
        "reading": [("System design primer", "https://github.com/donnemartin/system-design-primer")],
    },
    {
        "slug": "load-balancing", "level": "core", "title": "Load balancers", "scene": "fanout",
        "summary": "A load balancer spreads requests across servers and hides failures. The interesting decisions are where it sits, how it picks a server, and what happens when the balancer itself dies.",
        "ideas": [
            "L4 balances on IP and port (fast, blind to content); L7 reads HTTP and can route by path, header or cookie.",
            "Algorithms: round robin, least connections, weighted, consistent hashing for sticky routing without server state.",
            "Health checks remove dead servers within seconds; a slow drain keeps in-flight requests alive.",
            "Two balancers in active-passive with a floating IP remove the balancer as a single point of failure.",
            "Sticky sessions are a smell; keep session state in a shared store instead.",
        ],
        "interview": ["Distinguish the public balancer from internal service-to-service balancing.", "Explain how TLS termination at the balancer changes what backends see.", "Mention DNS as the outermost balancer across regions."],
        "reading": [("Introduction to modern network load balancing", "https://blog.envoyproxy.io/introduction-to-modern-network-load-balancing-and-proxying-a57f6ff80236")],
    },
    {
        "slug": "caching", "level": "core", "title": "Caching", "scene": "cache",
        "summary": "A cache trades freshness for speed. Every caching conversation is about three questions: what to cache, when it expires, and what happens when it's wrong.",
        "ideas": [
            "Cache-aside: app checks cache, on miss reads the DB and writes the cache. Simple, tolerant of cache failure.",
            "Write-through keeps cache and DB consistent at the cost of write latency; write-back batches writes and risks loss.",
            "Eviction: LRU is the default; LFU for skewed access; TTL for anything that can go stale.",
            "Thundering herd: one hot key expiring makes thousands of requests hit the DB at once. Fix with request coalescing or jittered TTLs.",
            "Cache at every layer that helps: browser, CDN, gateway, application, database buffer pool.",
        ],
        "interview": ["Say the hit ratio you expect and what it does to DB load.", "Name a key that must never be cached (balances, permissions).", "Explain invalidation for one concrete write path."],
        "reading": [("Scaling Memcache at Facebook", "https://www.usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf")],
    },
    {
        "slug": "databases-and-replication", "level": "core", "title": "Databases, replication and sharding", "scene": "replication",
        "summary": "Choose relational by default, document or key-value when the access pattern is simple and the scale is huge. Replication buys availability and read capacity; sharding buys write capacity and pain.",
        "ideas": [
            "Primary–replica: writes to one node, replicated asynchronously; replicas lag by milliseconds to seconds.",
            "Read-your-own-writes: route a user's reads to the primary briefly after they write.",
            "Sharding keys: hash of user id spreads load evenly; range sharding keeps scans cheap but creates hot shards.",
            "Cross-shard joins and transactions are the real cost; design the key so the common queries stay on one shard.",
            "Celebrity problem: one hot key overwhelms one shard; split it or cache it.",
        ],
        "interview": ["Pick the shard key and justify it against the top three queries.", "Describe failover: who promotes the replica, how clients find it.", "Know the difference between consistency in ACID and consistency in CAP."],
        "reading": [("Designing Data-Intensive Applications (book site)", "https://dataintensive.net/")],
    },
    {
        "slug": "cap-and-consistency", "level": "core", "title": "CAP, consistency models and quorums", "scene": "replication",
        "summary": "During a network partition a distributed store must choose: refuse some requests (consistency) or serve possibly stale data (availability). Quorum reads and writes let you tune the middle.",
        "ideas": [
            "Partitions happen; the only real choice is CP vs AP behaviour while one is in progress.",
            "N replicas, W acknowledgements per write, R per read: W + R > N gives strong consistency; W=1 gives fast writes.",
            "Eventual consistency is fine for likes and feeds; unacceptable for balances and inventory.",
            "Vector clocks or last-write-wins resolve concurrent writes; both have failure stories worth knowing.",
            "Linearizable, sequential, causal, eventual: know the ladder and where common databases sit.",
        ],
        "interview": ["Map each feature of the system to the weakest consistency it can tolerate.", "Explain a read-repair or anti-entropy mechanism.", "Give one real example of an AP choice that hurt users."],
        "reading": [("Jepsen analyses", "https://jepsen.io/analyses"), ("Amazon Dynamo paper", "https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf")],
    },
    {
        "slug": "message-queues", "level": "core", "title": "Message queues and async processing", "scene": "queue",
        "summary": "A queue decouples producers from consumers so slow work never blocks the request path. It also introduces new questions: ordering, duplicates, and what to do with poison messages.",
        "ideas": [
            "Use a queue when work can finish later: emails, thumbnails, notifications, analytics.",
            "At-least-once delivery is the norm; consumers must be idempotent (dedupe by message id).",
            "Ordering is per partition/key, never global; choose the key so related events stay in order.",
            "Backpressure: bounded queues, consumer autoscaling, and dead-letter queues for repeated failures.",
            "Pub/sub fans one event out to many consumers; point-to-point hands each message to one worker.",
        ],
        "interview": ["State delivery guarantee and idempotency strategy in the same breath.", "Show where the queue sits on the diagram and what happens if it is down.", "Say how you'd monitor lag."],
        "reading": [("Kafka design", "https://kafka.apache.org/documentation/#design")],
    },
    {
        "slug": "rate-limiting", "level": "core", "title": "Rate limiting", "scene": "bucket",
        "summary": "A rate limiter protects a service from abuse and overload by rejecting requests over a threshold. The algorithm choice is about burst tolerance and memory; the placement is about where you can afford to reject.",
        "ideas": [
            "Token bucket: refill at a rate, spend per request, allows bursts up to bucket size. The most common choice.",
            "Sliding window log is exact but memory-heavy; sliding window counter approximates it cheaply.",
            "Store counters in a fast shared store (Redis) so every gateway instance sees the same numbers.",
            "Return 429 with Retry-After; distinguish per-user, per-IP and per-endpoint limits.",
            "Race conditions on increment-and-check: use atomic operations or Lua scripts.",
        ],
        "interview": ["Choose the identity (user id, API key, IP) and explain its weakness.", "Explain what happens in a multi-region deployment.", "Mention that the limiter itself must not become the bottleneck."],
        "reading": [("Stripe: scaling your API with rate limiters", "https://stripe.com/blog/rate-limiters")],
    },
    {
        "slug": "consistent-hashing", "level": "core", "title": "Consistent hashing", "scene": "ring",
        "summary": "Naive hashing (key mod N) remaps almost every key when a server is added or removed. Consistent hashing places servers and keys on a ring so only the keys next to the change move.",
        "ideas": [
            "Hash both servers and keys onto a ring; a key belongs to the first server clockwise from it.",
            "Adding a server moves only the keys between it and its predecessor: about 1/N of the data.",
            "Virtual nodes (each server appears many times on the ring) smooth out uneven gaps and let bigger servers take more.",
            "Used for caches, distributed stores and load balancers with sticky routing.",
            "Replication: store each key on the next K servers clockwise.",
        ],
        "interview": ["Draw the ring and show a key moving when a node joins.", "Explain why virtual nodes help with heterogeneous hardware.", "Contrast with rendezvous hashing in one sentence."],
        "reading": [("Consistent hashing explained", "https://tom-e-white.com/2007/11/consistent-hashing.html")],
    },
    {
        "slug": "unique-ids", "level": "advanced", "title": "Unique ID generation at scale", "scene": "numbers",
        "summary": "Auto-increment doesn't survive sharding. You need IDs that are unique across machines, roughly time-ordered, and generated without coordination.",
        "ideas": [
            "UUID v4: 128 bits, no coordination, but random ordering hurts index locality.",
            "Snowflake-style: timestamp bits + machine id bits + sequence bits in a 64-bit integer; sortable and compact.",
            "Ticket servers: a database that hands out ranges; simple, but a coordination point.",
            "Clock skew is the failure mode for time-based IDs; refuse to generate when the clock goes backwards.",
            "Decide early whether IDs may leak information (creation time, volume).",
        ],
        "interview": ["Do the bit budget: how many years, machines and IDs per millisecond.", "Explain what happens when two generators get the same machine id.", "Relate ordering to database index performance."],
        "reading": [("Twitter Snowflake", "https://blog.twitter.com/engineering/en_us/a/2010/announcing-snowflake")],
    },
    {
        "slug": "url-shortener", "level": "advanced", "title": "Case study: URL shortener", "scene": "cache",
        "summary": "The classic warm-up case: a write-light, read-heavy service where the whole design hinges on key generation and caching the redirect path.",
        "ideas": [
            "Two endpoints: create (POST long → short) and redirect (GET short → 301/302).",
            "Key: base-62 encode a unique ID (7 characters ≈ 3.5 trillion keys) or hash and truncate with collision checks.",
            "Reads dominate; cache short→long aggressively, and put the redirect behind a CDN if it's public.",
            "301 is cached by browsers (less load, no analytics); 302 keeps every click visible to you.",
            "Analytics are an async pipeline off the redirect path, not a synchronous write.",
        ],
        "interview": ["Estimate storage for 100 million new URLs a year.", "Explain the trade-off in 301 vs 302 for your product goals.", "Handle a custom-alias collision."],
        "reading": [("Design a URL shortener (Educative)", "https://www.educative.io/courses/grokking-the-system-design-interview")],
    },
    {
        "slug": "key-value-store", "level": "advanced", "title": "Case study: distributed key-value store", "scene": "ring",
        "summary": "Put together consistent hashing, replication, quorums and failure detection and you have a Dynamo-style store. The interview is about how those pieces interact.",
        "ideas": [
            "Partition with consistent hashing; replicate to the next N nodes on the ring.",
            "Tune W and R per use case; sloppy quorums and hinted handoff keep writes flowing during failures.",
            "Detect failures with gossip; a node is down when enough peers agree, not when one does.",
            "Write path: commit log → memtable → SSTable on disk; reads check bloom filters before touching disk.",
            "Merkle trees make anti-entropy repair cheap: compare hashes, sync only the differing ranges.",
        ],
        "interview": ["Walk a write from client to disk on three replicas.", "Show the read path with a stale replica and how it repairs.", "Explain compaction and why it matters for read latency."],
        "reading": [("Dynamo paper", "https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf"), ("Cassandra architecture", "https://cassandra.apache.org/doc/latest/cassandra/architecture/")],
    },
    {
        "slug": "notification-system", "level": "advanced", "title": "Case study: notification system", "scene": "queue",
        "summary": "Push, SMS and email each go through a different third party with different failure modes. The design is a queue per channel, a preference check, and relentless deduplication.",
        "ideas": [
            "Producers publish an event; a notification service resolves recipients, checks preferences and rate limits, then enqueues per channel.",
            "Each channel has its own workers and third-party gateway (APNs, FCM, SMS provider, SMTP).",
            "Retries with backoff for transient failures; a dead-letter queue for the rest; never retry a 4xx forever.",
            "Idempotency keys stop a user getting the same push twice after a worker crash.",
            "Templates and localisation live in the service, not in the producers.",
        ],
        "interview": ["Explain how you avoid notifying a user who opted out five seconds ago.", "Describe priority: an OTP must beat a marketing push.", "Show where analytics (delivered, opened) come from."],
        "reading": [("Firebase Cloud Messaging architecture", "https://firebase.google.com/docs/cloud-messaging/fcm-architecture")],
    },
    {
        "slug": "news-feed", "level": "advanced", "title": "Case study: news feed", "scene": "fanout",
        "summary": "A feed is a read-heavy merge of many users' posts. The central decision is fan-out on write (precompute each follower's feed) versus fan-out on read (merge at request time), and most real systems do both.",
        "ideas": [
            "Fan-out on write: when a user posts, push the post id into every follower's feed cache. Fast reads, expensive for celebrities.",
            "Fan-out on read: build the feed at request time from followed users' recent posts. Cheap writes, slow reads.",
            "Hybrid: precompute for normal users, merge celebrities' posts at read time.",
            "Feed cache holds ids only; hydrate posts and users from separate caches to keep memory small.",
            "Ranking is a separate service consuming the candidate list; keep it out of the storage path.",
        ],
        "interview": ["Estimate fan-out cost for a user with 10 million followers.", "Explain pagination with cursors, not offsets.", "Say how deleted posts disappear from precomputed feeds."],
        "reading": [("Twitter timelines at scale (talk)", "https://www.infoq.com/presentations/Twitter-Timeline-Scalability/")],
    },
]


def by_level() -> list[tuple[str, str, list[dict]]]:
    return [(key, label, [t for t in TOPICS if t["level"] == key]) for key, label in LEVELS]


def get(slug: str) -> dict | None:
    for i, t in enumerate(TOPICS):
        if t["slug"] == slug:
            out = dict(t)
            out["prev"] = TOPICS[i - 1] if i > 0 else None
            out["next"] = TOPICS[i + 1] if i + 1 < len(TOPICS) else None
            out["index"] = i + 1
            return out
    return None
