import json
import re
from pathlib import Path

# Complete C++ implementations for all 26 patterns
CPP_CODES = {
  "two-pointers": [
    "vector<int> twoSumSorted(vector<int>& arr, int target) {",
    "    int left = 0;",
    "    int right = arr.size() - 1;",
    "    while (left < right) {",
    "        int curr_sum = arr[left] + arr[right];",
    "        if (curr_sum == target) {",
    "            return {left, right};",
    "        } else if (curr_sum > target) {",
    "            right--;",
    "        } else {",
    "            left++;",
    "        }",
    "    }",
    "    return {};",
    "}"
  ],
  "sliding-window": [
    "int maxSubArrayOfSizeK(int k, vector<int>& arr) {",
    "    int max_sum = 0, window_sum = 0;",
    "    int window_start = 0;",
    "    for (int window_end = 0; window_end < arr.size(); window_end++) {",
    "        window_sum += arr[window_end];",
    "        if (window_end >= k - 1) {",
    "            max_sum = max(max_sum, window_sum);",
    "            window_sum -= arr[window_start];",
    "            window_start++;",
    "        }",
    "    }",
    "    return max_sum;",
    "}"
  ],
  "fast-slow-pointers": [
    "bool hasCycle(ListNode* head) {",
    "    ListNode* slow = head;",
    "    ListNode* fast = head;",
    "    while (fast && fast->next) {",
    "        slow = slow->next;",
    "        fast = fast->next->next;",
    "        if (slow == fast) return true;",
    "    }",
    "    return false;",
    "}"
  ],
  "linked-list-reversal": [
    "ListNode* reverseList(ListNode* head) {",
    "    ListNode* prev = nullptr;",
    "    ListNode* curr = head;",
    "    while (curr != nullptr) {",
    "        ListNode* nxt = curr->next;",
    "        curr->next = prev;",
    "        prev = curr;",
    "        curr = nxt;",
    "    }",
    "    return prev;",
    "}"
  ],
  "backtracking": [
    "vector<vector<int>> subsets(vector<int>& nums) {",
    "    vector<vector<int>> res;",
    "    vector<int> path;",
    "    auto backtrack = [&](auto& self, int start) -> void {",
    "        res.push_back(path);",
    "        for (int i = start; i < nums.size(); i++) {",
    "            path.push_back(nums[i]);",
    "            self(self, i + 1);",
    "            path.pop_back();",
    "        }",
    "    };",
    "    backtrack(backtrack, 0);",
    "    return res;",
    "}"
  ],
  "union-find": [
    "int find(int i, vector<int>& parent) {",
    "    if (parent[i] == i) return i;",
    "    return parent[i] = find(parent[i], parent);",
    "}",
    "void unionNodes(int u, int v, vector<int>& parent) {",
    "    int root_u = find(u, parent);",
    "    int root_v = find(v, parent);",
    "    if (root_u != root_v) parent[root_v] = root_u;",
    "}"
  ],
  "topological-sort": [
    "vector<int> topologicalSort(int n, vector<pair<int,int>>& edges) {",
    "    vector<int> in_degree(n, 0);",
    "    for (auto& [u, v] : edges) in_degree[v]++;",
    "    queue<int> q;",
    "    for (int i = 0; i < n; i++) if (in_degree[i] == 0) q.push(i);",
    "    vector<int> order;",
    "    while (!q.empty()) {",
    "        int u = q.front(); q.pop();",
    "        order.push_back(u);",
    "        for (int v : adj[u]) if (--in_degree[v] == 0) q.push(v);",
    "    }",
    "    return order;",
    "}"
  ],
  "shortest-path": [
    "vector<int> dijkstra(int n, vector<vector<pair<int,int>>>& graph, int start) {",
    "    vector<int> dist(n, 1e9);",
    "    dist[start] = 0;",
    "    priority_queue<pair<int,int>, vector<pair<int,int>>, greater<>> pq;",
    "    pq.push({0, start});",
    "    while (!pq.empty()) {",
    "        auto [d, u] = pq.top(); pq.pop();",
    "        if (d > dist[u]) continue;",
    "        for (auto& [v, weight] : graph[u]) {",
    "            if (dist[u] + weight < dist[v]) {",
    "                dist[v] = dist[u] + weight;",
    "                pq.push({dist[v], v});",
    "            }",
    "        }",
    "    }",
    "    return dist;",
    "}"
  ],
  "dp-knapsack": [
    "int knapsack(vector<int>& weights, vector<int>& values, int W) {",
    "    int N = weights.size();",
    "    vector<vector<int>> dp(N + 1, vector<int>(W + 1, 0));",
    "    for (int i = 1; i <= N; i++) {",
    "        int wt = weights[i-1], val = values[i-1];",
    "        for (int w = 1; w <= W; w++) {",
    "            if (wt <= w) dp[i][w] = max(dp[i-1][w], val + dp[i-1][w-wt]);",
    "            else dp[i][w] = dp[i-1][w];",
    "        }",
    "    }",
    "    return dp[N][W];",
    "}"
  ],
  "dp-1d": [
    "int climbStairs(int n) {",
    "    if (n <= 2) return n;",
    "    vector<int> dp(n + 1, 0);",
    "    dp[1] = 1; dp[2] = 2;",
    "    for (int i = 3; i <= n; i++) {",
    "        dp[i] = dp[i-1] + dp[i-2];",
    "    }",
    "    return dp[n];",
    "}"
  ],
  "dp-2d": [
    "int uniquePaths(int m, int n) {",
    "    vector<vector<int>> dp(m, vector<int>(n, 1));",
    "    for (int r = 1; r < m; r++) {",
    "        for (int c = 1; c < n; c++) {",
    "            dp[r][c] = dp[r-1][c] + dp[r][c-1];",
    "        }",
    "    }",
    "    return dp[m-1][n-1];",
    "}"
  ],
  "dp-subsequence": [
    "int longestCommonSubsequence(string s1, string s2) {",
    "    int m = s1.size(), n = s2.size();",
    "    vector<vector<int>> dp(m + 1, vector<int>(n + 1, 0));",
    "    for (int i = 1; i <= m; i++) {",
    "        for (int j = 1; j <= n; j++) {",
    "            if (s1[i-1] == s2[j-1]) dp[i][j] = 1 + dp[i-1][j-1];",
    "            else dp[i][j] = max(dp[i-1][j], dp[i][j-1]);",
    "        }",
    "    }",
    "    return dp[m][n];",
    "}"
  ],
  "prefix-sum": [
    "int subarraySum(vector<int>& nums, int k) {",
    "    int count = 0, curr_sum = 0;",
    "    unordered_map<int, int> seen = {{0, 1}};",
    "    for (int x : nums) {",
    "        curr_sum += x;",
    "        if (seen.count(curr_sum - k)) count += seen[curr_sum - k];",
    "        seen[curr_sum]++;",
    "    }",
    "    return count;",
    "}"
  ],
  "sorting-greedy": [
    "int minMeetingRooms(vector<vector<int>>& intervals) {",
    "    vector<int> starts, ends;",
    "    for (auto& i : intervals) { starts.push_back(i[0]); ends.push_back(i[1]); }",
    "    sort(starts.begin(), starts.end());",
    "    sort(ends.begin(), ends.end());",
    "    int s = 0, e = 0, rooms = 0;",
    "    while (s < intervals.size()) {",
    "        if (starts[s] < ends[e]) rooms++;",
    "        else e++;",
    "        s++;",
    "    }",
    "    return rooms;",
    "}"
  ],
  "merge-intervals": [
    "vector<vector<int>> merge(vector<vector<int>>& intervals) {",
    "    sort(intervals.begin(), intervals.end());",
    "    vector<vector<int>> merged = {intervals[0]};",
    "    for (int i = 1; i < intervals.size(); i++) {",
    "        auto& prev = merged.back();",
    "        if (intervals[i][0] <= prev[1]) prev[1] = max(prev[1], intervals[i][1]);",
    "        else merged.push_back(intervals[i]);",
    "    }",
    "    return merged;",
    "}"
  ],
  "cyclic-sort": [
    "vector<int> cyclicSort(vector<int>& nums) {",
    "    int i = 0;",
    "    while (i < nums.size()) {",
    "        int correct_idx = nums[i] - 1;",
    "        if (nums[i] != nums[correct_idx]) swap(nums[i], nums[correct_idx]);",
    "        else i++;",
    "    }",
    "    return nums;",
    "}"
  ],
  "monotonic-stack": [
    "vector<int> nextGreater(vector<int>& nums) {",
    "    stack<int> st;",
    "    vector<int> res(nums.size(), -1);",
    "    for (int i = 0; i < nums.size(); i++) {",
    "        while (!st.empty() && nums[st.top()] < nums[i]) {",
    "            res[st.top()] = nums[i];",
    "            st.pop();",
    "        }",
    "        st.push(i);",
    "    }",
    "    return res;",
    "}"
  ],
  "monotonic-deque": [
    "vector<int> maxSlidingWindow(vector<int>& nums, int k) {",
    "    deque<int> q;",
    "    vector<int> res;",
    "    for (int i = 0; i < nums.size(); i++) {",
    "        while (!q.empty() && nums[q.back()] < nums[i]) q.pop_back();",
    "        q.push_back(i);",
    "        if (q.front() <= i - k) q.pop_front();",
    "        if (i >= k - 1) res.push_back(nums[q.front()]);",
    "    }",
    "    return res;",
    "}"
  ],
  "binary-search": [
    "int binarySearch(vector<int>& arr, int target) {",
    "    int low = 0, high = arr.size() - 1;",
    "    while (low <= high) {",
    "        int mid = low + (high - low) / 2;",
    "        if (arr[mid] == target) return mid;",
    "        else if (arr[mid] < target) low = mid + 1;",
    "        else high = mid - 1;",
    "    }",
    "    return -1;",
    "}"
  ],
  "binary-search-answer": [
    "int minEatingSpeed(vector<int>& piles, int h) {",
    "    int low = 1, high = *max_element(piles.begin(), piles.end());",
    "    int ans = high;",
    "    while (low <= high) {",
    "        int mid = low + (high - low) / 2;",
    "        if (canFinish(piles, mid, h)) { ans = mid; high = mid - 1; }",
    "        else low = mid + 1;",
    "    }",
    "    return ans;",
    "}"
  ],
  "top-k-heap": [
    "int findKthLargest(vector<int>& nums, int k) {",
    "    priority_queue<int, vector<int>, greater<int>> min_heap;",
    "    for (int x : nums) {",
    "        min_heap.push(x);",
    "        if (min_heap.size() > k) min_heap.pop();",
    "    }",
    "    return min_heap.top();",
    "}"
  ],
  "tree-dfs": [
    "void inorder(TreeNode* node, vector<int>& res) {",
    "    if (!node) return;",
    "    inorder(node->left, res);",
    "    res.push_back(node->val);",
    "    inorder(node->right, res);",
    "}"
  ],
  "tree-bfs": [
    "vector<vector<int>> levelOrder(TreeNode* root) {",
    "    if (!root) return {};",
    "    queue<TreeNode*> q; q.push(root);",
    "    vector<vector<int>> res;",
    "    while (!q.empty()) {",
    "        int sz = q.size();",
    "        vector<int> level;",
    "        while (sz--) {",
    "            TreeNode* node = q.front(); q.pop();",
    "            level.push_back(node->val);",
    "            if (node->left) q.push(node->left);",
    "            if (node->right) q.push(node->right);",
    "        }",
    "        res.push_back(level);",
    "    }",
    "    return res;",
    "}"
  ],
  "trie": [
    "bool startsWith(TrieNode* root, string prefix) {",
    "    TrieNode* curr = root;",
    "    for (char c : prefix) {",
    "        if (!curr->children.count(c)) return false;",
    "        curr = curr->children[c];",
    "    }",
    "    return true;",
    "}"
  ],
  "graph-traversal": [
    "void bfs(unordered_map<int, vector<int>>& graph, int start) {",
    "    queue<int> q; unordered_set<int> visited = {start};",
    "    q.push(start);",
    "    while (!q.empty()) {",
    "        int curr = q.front(); q.pop();",
    "        for (int neighbor : graph[curr]) {",
    "            if (!visited.count(neighbor)) {",
    "                visited.insert(neighbor);",
    "                q.push(neighbor);",
    "            }",
    "        }",
    "    }",
    "}"
  ],
  "bit-manipulation": [
    "bool isPowerOfTwo(int n) {",
    "    if (n <= 0) return false;",
    "    // n & (n - 1) clears lowest 1-bit",
    "    int cleared = n & (n - 1);",
    "    return cleared == 0;",
    "}"
  ]
}

# Complete Java implementations for all 26 patterns
JAVA_CODES = {
  "two-pointers": [
    "public int[] twoSumSorted(int[] arr, int target) {",
    "    int left = 0;",
    "    int right = arr.length - 1;",
    "    while (left < right) {",
    "        int curr_sum = arr[left] + arr[right];",
    "        if (curr_sum == target) {",
    "            return new int[]{left, right};",
    "        } else if (curr_sum > target) {",
    "            right--;",
    "        } else {",
    "            left++;",
    "        }",
    "    }",
    "    return null;",
    "}"
  ],
  "sliding-window": [
    "public int maxSubArrayOfSizeK(int k, int[] arr) {",
    "    int max_sum = 0, window_sum = 0;",
    "    int window_start = 0;",
    "    for (int window_end = 0; window_end < arr.length; window_end++) {",
    "        window_sum += arr[window_end];",
    "        if (window_end >= k - 1) {",
    "            max_sum = Math.max(max_sum, window_sum);",
    "            window_sum -= arr[window_start];",
    "            window_start++;",
    "        }",
    "    }",
    "    return max_sum;",
    "}"
  ],
  "fast-slow-pointers": [
    "public boolean hasCycle(ListNode head) {",
    "    ListNode slow = head;",
    "    ListNode fast = head;",
    "    while (fast != null && fast.next != null) {",
    "        slow = slow.next;",
    "        fast = fast.next.next;",
    "        if (slow == fast) return true;",
    "    }",
    "    return false;",
    "}"
  ],
  "linked-list-reversal": [
    "public ListNode reverseList(ListNode head) {",
    "    ListNode prev = null;",
    "    ListNode curr = head;",
    "    while (curr != null) {",
    "        ListNode nxt = curr.next;",
    "        curr.next = prev;",
    "        prev = curr;",
    "        curr = nxt;",
    "    }",
    "    return prev;",
    "}"
  ],
  "backtracking": [
    "public List<List<Integer>> subsets(int[] nums) {",
    "    List<List<Integer>> res = new ArrayList<>();",
    "    backtrack(0, nums, new ArrayList<>(), res);",
    "    return res;",
    "}",
    "private void backtrack(int start, int[] nums, List<Integer> path, List<List<Integer>> res) {",
    "    res.add(new ArrayList<>(path));",
    "    for (int i = start; i < nums.length; i++) {",
    "        path.add(nums[i]);",
    "        backtrack(i + 1, nums, path, res);",
    "        path.remove(path.size() - 1);",
    "    }",
    "}"
  ],
  "union-find": [
    "public int find(int i, int[] parent) {",
    "    if (parent[i] == i) return i;",
    "    return parent[i] = find(parent[i], parent);",
    "}",
    "public void union(int u, int v, int[] parent) {",
    "    int root_u = find(u, parent);",
    "    int root_v = find(v, parent);",
    "    if (root_u != root_v) parent[root_v] = root_u;",
    "}"
  ],
  "topological-sort": [
    "public List<Integer> topologicalSort(int n, int[][] edges) {",
    "    int[] in_degree = new int[n];",
    "    for (int[] e : edges) in_degree[e[1]]++;",
    "    Queue<Integer> queue = new LinkedList<>();",
    "    for (int i = 0; i < n; i++) if (in_degree[i] == 0) queue.offer(i);",
    "    List<Integer> order = new ArrayList<>();",
    "    while (!queue.isEmpty()) {",
    "        int u = queue.poll();",
    "        order.add(u);",
    "        for (int v : adj.get(u)) if (--in_degree[v] == 0) queue.offer(v);",
    "    }",
    "    return order;",
    "}"
  ],
  "shortest-path": [
    "public int[] dijkstra(int n, List<List<int[]>> graph, int start) {",
    "    int[] dist = new int[n];",
    "    Arrays.fill(dist, Integer.MAX_VALUE);",
    "    dist[start] = 0;",
    "    PriorityQueue<int[]> pq = new PriorityQueue<>((a, b) -> a[0] - b[0]);",
    "    pq.offer(new int[]{0, start});",
    "    while (!pq.isEmpty()) {",
    "        int[] curr = pq.poll();",
    "        int d = curr[0], u = curr[1];",
    "        if (d > dist[u]) continue;",
    "        for (int[] edge : graph.get(u)) {",
    "            int v = edge[0], weight = edge[1];",
    "            if (dist[u] + weight < dist[v]) {",
    "                dist[v] = dist[u] + weight;",
    "                pq.offer(new int[]{dist[v], v});",
    "            }",
    "        }",
    "    }",
    "    return dist;",
    "}"
  ],
  "dp-knapsack": [
    "public int knapsack(int[] weights, int[] values, int W) {",
    "    int N = weights.length;",
    "    int[][] dp = new int[N + 1][W + 1];",
    "    for (int i = 1; i <= N; i++) {",
    "        int wt = weights[i-1], val = values[i-1];",
    "        for (int w = 1; w <= W; w++) {",
    "            if (wt <= w) dp[i][w] = Math.max(dp[i-1][w], val + dp[i-1][w-wt]);",
    "            else dp[i][w] = dp[i-1][w];",
    "        }",
    "    }",
    "    return dp[N][W];",
    "}"
  ],
  "dp-1d": [
    "public int climbStairs(int n) {",
    "    if (n <= 2) return n;",
    "    int[] dp = new int[n + 1];",
    "    dp[1] = 1; dp[2] = 2;",
    "    for (int i = 3; i <= n; i++) {",
    "        dp[i] = dp[i-1] + dp[i-2];",
    "    }",
    "    return dp[n];",
    "}"
  ],
  "dp-2d": [
    "public int uniquePaths(int m, int n) {",
    "    int[][] dp = new int[m][n];",
    "    for (int[] row : dp) Arrays.fill(row, 1);",
    "    for (int r = 1; r < m; r++) {",
    "        for (int c = 1; c < n; c++) {",
    "            dp[r][c] = dp[r-1][c] + dp[r][c-1];",
    "        }",
    "    }",
    "    return dp[m-1][n-1];",
    "}"
  ],
  "dp-subsequence": [
    "public int longestCommonSubsequence(String s1, String s2) {",
    "    int m = s1.length(), n = s2.length();",
    "    int[][] dp = new int[m + 1][n + 1];",
    "    for (int i = 1; i <= m; i++) {",
    "        for (int j = 1; j <= n; j++) {",
    "            if (s1.charAt(i-1) == s2.charAt(j-1)) dp[i][j] = 1 + dp[i-1][j-1];",
    "            else dp[i][j] = Math.max(dp[i-1][j], dp[i][j-1]);",
    "        }",
    "    }",
    "    return dp[m][n];",
    "}"
  ],
  "prefix-sum": [
    "public int subarraySum(int[] nums, int k) {",
    "    int count = 0, curr_sum = 0;",
    "    Map<Integer, Integer> seen = new HashMap<>();",
    "    seen.put(0, 1);",
    "    for (int x : nums) {",
    "        curr_sum += x;",
    "        if (seen.containsKey(curr_sum - k)) count += seen.get(curr_sum - k);",
    "        seen.put(curr_sum, seen.getOrDefault(curr_sum, 0) + 1);",
    "    }",
    "    return count;",
    "}"
  ],
  "sorting-greedy": [
    "public int minMeetingRooms(int[][] intervals) {",
    "    int[] starts = new int[intervals.length];",
    "    int[] ends = new int[intervals.length];",
    "    for (int i = 0; i < intervals.length; i++) { starts[i] = intervals[i][0]; ends[i] = intervals[i][1]; }",
    "    Arrays.sort(starts);",
    "    Arrays.sort(ends);",
    "    int s = 0, e = 0, rooms = 0;",
    "    while (s < intervals.length) {",
    "        if (starts[s] < ends[e]) rooms++;",
    "        else e++;",
    "        s++;",
    "    }",
    "    return rooms;",
    "}"
  ],
  "merge-intervals": [
    "public int[][] merge(int[][] intervals) {",
    "    Arrays.sort(intervals, (a, b) -> Integer.compare(a[0], b[0]));",
    "    List<int[]> merged = new ArrayList<>();",
    "    merged.add(intervals[0]);",
    "    for (int i = 1; i < intervals.length; i++) {",
    "        int[] prev = merged.get(merged.size() - 1);",
    "        if (intervals[i][0] <= prev[1]) prev[1] = Math.max(prev[1], intervals[i][1]);",
    "        else merged.add(intervals[i]);",
    "    }",
    "    return merged.toArray(new int[merged.size()][]);",
    "}"
  ],
  "cyclic-sort": [
    "public int[] cyclicSort(int[] nums) {",
    "    int i = 0;",
    "    while (i < nums.length) {",
    "        int correct_idx = nums[i] - 1;",
    "        if (nums[i] != nums[correct_idx]) {",
    "            int tmp = nums[i]; nums[i] = nums[correct_idx]; nums[correct_idx] = tmp;",
    "        } else i++;",
    "    }",
    "    return nums;",
    "}"
  ],
  "monotonic-stack": [
    "public int[] nextGreater(int[] nums) {",
    "    Stack<Integer> stack = new Stack<>();",
    "    int[] res = new int[nums.length];",
    "    Arrays.fill(res, -1);",
    "    for (int i = 0; i < nums.length; i++) {",
    "        while (!stack.isEmpty() && nums[stack.peek()] < nums[i]) res[stack.pop()] = nums[i];",
    "        stack.push(i);",
    "    }",
    "    return res;",
    "}"
  ],
  "monotonic-deque": [
    "public int[] maxSlidingWindow(int[] nums, int k) {",
    "    Deque<Integer> q = new ArrayDeque<>();",
    "    int[] res = new int[nums.length - k + 1];",
    "    int idx = 0;",
    "    for (int i = 0; i < nums.length; i++) {",
    "        while (!q.isEmpty() && nums[q.peekLast()] < nums[i]) q.pollLast();",
    "        q.offerLast(i);",
    "        if (q.peekFirst() <= i - k) q.pollFirst();",
    "        if (i >= k - 1) res[idx++] = nums[q.peekFirst()];",
    "    }",
    "    return res;",
    "}"
  ],
  "binary-search": [
    "public int binarySearch(int[] arr, int target) {",
    "    int low = 0, high = arr.length - 1;",
    "    while (low <= high) {",
    "        int mid = low + (high - low) / 2;",
    "        if (arr[mid] == target) return mid;",
    "        else if (arr[mid] < target) low = mid + 1;",
    "        else high = mid - 1;",
    "    }",
    "    return -1;",
    "}"
  ],
  "binary-search-answer": [
    "public int minEatingSpeed(int[] piles, int h) {",
    "    int low = 1, high = 1000000000;",
    "    for (int p : piles) high = Math.max(high, p);",
    "    int ans = high;",
    "    while (low <= high) {",
    "        int mid = low + (high - low) / 2;",
    "        if (canFinish(piles, mid, h)) { ans = mid; high = mid - 1; }",
    "        else low = mid + 1;",
    "    }",
    "    return ans;",
    "}"
  ],
  "top-k-heap": [
    "public int findKthLargest(int[] nums, int k) {",
    "    PriorityQueue<Integer> minHeap = new PriorityQueue<>();",
    "    for (int x : nums) {",
    "        minHeap.offer(x);",
    "        if (minHeap.size() > k) minHeap.poll();",
    "    }",
    "    return minHeap.peek();",
    "}"
  ],
  "tree-dfs": [
    "public void inorder(TreeNode node, List<Integer> res) {",
    "    if (node == null) return;",
    "    inorder(node.left, res);",
    "    res.add(node.val);",
    "    inorder(node.right, res);",
    "}"
  ],
  "tree-bfs": [
    "public List<List<Integer>> levelOrder(TreeNode root) {",
    "    if (root == null) return new ArrayList<>();",
    "    Queue<TreeNode> queue = new LinkedList<>();",
    "    queue.offer(root);",
    "    List<List<Integer>> res = new ArrayList<>();",
    "    while (!queue.isEmpty()) {",
    "        int size = queue.size();",
    "        List<Integer> level = new ArrayList<>();",
    "        for (int i = 0; i < size; i++) {",
    "            TreeNode node = queue.poll();",
    "            level.add(node.val);",
    "            if (node.left != null) queue.offer(node.left);",
    "            if (node.right != null) queue.offer(node.right);",
    "        }",
    "        res.add(level);",
    "    }",
    "    return res;",
    "}"
  ],
  "trie": [
    "public boolean startsWith(TrieNode root, String prefix) {",
    "    TrieNode curr = root;",
    "    for (char c : prefix.toCharArray()) {",
    "        if (!curr.children.containsKey(c)) return false;",
    "        curr = curr.children.get(c);",
    "    }",
    "    return true;",
    "}"
  ],
  "graph-traversal": [
    "public void bfs(Map<Integer, List<Integer>> graph, int start) {",
    "    Queue<Integer> queue = new LinkedList<>();",
    "    Set<Integer> visited = new HashSet<>();",
    "    visited.add(start);",
    "    queue.offer(start);",
    "    while (!queue.isEmpty()) {",
    "        int curr = queue.poll();",
    "        for (int neighbor : graph.getOrDefault(curr, new ArrayList<>())) {",
    "            if (!visited.contains(neighbor)) {",
    "                visited.add(neighbor);",
    "                queue.offer(neighbor);",
    "            }",
    "        }",
    "    }",
    "}"
  ],
  "bit-manipulation": [
    "public boolean isPowerOfTwo(int n) {",
    "    if (n <= 0) return false;",
    "    // n & (n - 1) clears lowest 1-bit",
    "    int cleared = n & (n - 1);",
    "    return cleared == 0;",
    "}"
  ]
}

# Attach C++ and Java to each pattern
from generate_all_patterns import PATTERNS, TEMPLATE

for k in PATTERNS:
    PATTERNS[k]["code_cpp"] = CPP_CODES.get(k, PATTERNS[k]["code"])
    PATTERNS[k]["code_java"] = JAVA_CODES.get(k, PATTERNS[k]["code"])

print(f"Loaded C++ and Java code across all {len(PATTERNS)} patterns.")

# Update TEMPLATE with language tabs
updated_template = TEMPLATE

# 1. Add CSS for tabs
tab_css = """
.pt-lang-tabs {
  display: inline-flex;
  gap: 4px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 2px;
}
.pt-lang-btn {
  background: transparent;
  border: none;
  color: #8b949e;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.pt-lang-btn:hover {
  color: #f0f6fc;
}
.pt-lang-btn.active {
  color: #58a6ff;
  background: rgba(56, 139, 253, 0.15);
  font-weight: 700;
}
"""
updated_template = updated_template.replace("</style>", tab_css + "\n</style>")

# 2. Update Left Pane Header
old_header = """      <div class="pt-pane-header">
        <span>Python Implementation</span>
        <span class="pt-subtag" id="pt-active-func">main()</span>
      </div>"""

new_header = """      <div class="pt-pane-header" style="display:flex;justify-content:space-between;align-items:center;">
        <div class="pt-lang-tabs" id="pt-lang-tabs">
          <button type="button" class="pt-lang-btn active" data-lang="python">🐍 Python</button>
          <button type="button" class="pt-lang-btn" data-lang="cpp">⚡ C++</button>
          <button type="button" class="pt-lang-btn" data-lang="java">☕ Java</button>
        </div>
        <span class="pt-subtag" id="pt-active-func">main()</span>
      </div>"""

updated_template = updated_template.replace(old_header, new_header)

# 3. Update JavaScript to support active language switching and syntax highlighting
old_js_start = """  // Resolve matching pattern model
  let model = DB[slug] || DB["two-pointers"];
  let currentStep = 0;"""

new_js_start = """  // Resolve matching pattern model
  let model = DB[slug] || DB["two-pointers"];
  let currentStep = 0;
  let activeLang = 'python'; // 'python' | 'cpp' | 'java'"""

updated_template = updated_template.replace(old_js_start, new_js_start)

old_highlight = """  // Helper syntax highlighter
  function highlightCode(raw) {
    return raw
      .replace(/ (def|for|while|if|elif|else|return|in|not|and|or) /g, '<span class="pt-kw">$1</span>')
      .replace(/ (two_sum_sorted|max_sub_array_of_size_k|has_cycle|reverse_list|subsets|find_and_union|topological_sort|dijkstra|knapsack|climb_stairs|unique_paths|longest_common_subsequence|subarray_sum|min_meeting_rooms|merge|cyclic_sort|next_greater|max_sliding_window|binary_search|min_eating_speed|find_kth_largest|inorder|level_order|starts_with|bfs|is_power_of_two) /g, '<span class="pt-fn">$1</span>')
      .replace(/ (\d+) /g, '<span class="pt-num">$1</span>')
      .replace(/(#.*$)/g, '<span class="pt-cm">$1</span>')
      .replace(/('[^']*')/g, '<span class="pt-str">$1</span>');
  }"""

new_highlight = """  // Helper syntax highlighter supporting Python, C++, and Java
  function highlightCode(raw, lang) {
    if (lang === 'cpp') {
      return raw
        .replace(/\\b(int|void|bool|auto|vector|string|unordered_map|unordered_set|queue|stack|priority_queue|pair|ListNode|TreeNode|TrieNode)\\b/g, '<span class="pt-fn">$1</span>')
        .replace(/\\b(for|while|if|else|return|nullptr|true|false|new)\\b/g, '<span class="pt-kw">$1</span>')
        .replace(/\\b(\\d+)\\b/g, '<span class="pt-num">$1</span>')
        .replace(/(\\/\\/.*$)/g, '<span class="pt-cm">$1</span>')
        .replace(/("[^"]*")/g, '<span class="pt-str">$1</span>');
    }
    if (lang === 'java') {
      return raw
        .replace(/\\b(public|private|static|class|int|void|boolean|String|List|ArrayList|Map|HashMap|Set|HashSet|Queue|LinkedList|Deque|ArrayDeque|Stack|ListNode|TreeNode|TrieNode)\\b/g, '<span class="pt-fn">$1</span>')
        .replace(/\\b(for|while|if|else|return|null|true|false|new)\\b/g, '<span class="pt-kw">$1</span>')
        .replace(/\\b(\\d+)\\b/g, '<span class="pt-num">$1</span>')
        .replace(/(\\/\\/.*$)/g, '<span class="pt-cm">$1</span>')
        .replace(/("[^"]*")/g, '<span class="pt-str">$1</span>');
    }
    return raw
      .replace(/\\b(def|for|while|if|elif|else|return|in|not|and|or|None|True|False)\\b/g, '<span class="pt-kw">$1</span>')
      .replace(/\\b(two_sum_sorted|max_sub_array_of_size_k|has_cycle|reverse_list|subsets|find_and_union|topological_sort|dijkstra|knapsack|climb_stairs|unique_paths|longest_common_subsequence|subarray_sum|min_meeting_rooms|merge|cyclic_sort|next_greater|max_sliding_window|binary_search|min_eating_speed|find_kth_largest|inorder|level_order|starts_with|bfs|is_power_of_two)\\b/g, '<span class="pt-fn">$1</span>')
      .replace(/\\b(\\d+)\\b/g, '<span class="pt-num">$1</span>')
      .replace(/(#.*$)/g, '<span class="pt-cm">$1</span>')
      .replace(/('[^']*'|"[^"]*")/g, '<span class="pt-str">$1</span>');
  }"""

updated_template = updated_template.replace(old_highlight, new_highlight)

# Update renderCodeBox to use activeLang
old_render_code = """  // Render Full Code Block Once
  function renderCodeBox(activeLine) {
    let html = '';
    model.code.forEach((lineText, idx) => {
      const lineNum = idx + 1;
      const isExec = lineNum === activeLine;
      html += `
        <div class="pt-code-line ${isExec ? 'active-line' : ''}" id="code-line-${lineNum}">
          <span class="pt-line-num">${lineNum}</span>
          <span class="pt-exec-marker">${isExec ? '▶' : ''}</span>
          <span class="pt-code-content">${highlightCode(lineText)}</span>
        </div>
      `;
    });
    codeBox.innerHTML = html;
  }"""

new_render_code = """  // Render Full Code Block Once per Selected Language
  function renderCodeBox(activeLine) {
    let html = '';
    const codeLines = (activeLang === 'cpp' && model.code_cpp) ? model.code_cpp : 
                      (activeLang === 'java' && model.code_java) ? model.code_java : 
                      model.code;
    codeLines.forEach((lineText, idx) => {
      const lineNum = idx + 1;
      const isExec = lineNum === activeLine;
      html += `
        <div class="pt-code-line ${isExec ? 'active-line' : ''}" id="code-line-${lineNum}">
          <span class="pt-line-num">${lineNum}</span>
          <span class="pt-exec-marker">${isExec ? '▶' : ''}</span>
          <span class="pt-code-content">${highlightCode(lineText, activeLang)}</span>
        </div>
      `;
    });
    codeBox.innerHTML = html;
  }"""

updated_template = updated_template.replace(old_render_code, new_render_code)

# Add event listeners for language tabs
old_listeners = "  btnFirst.onclick = function() {"
new_listeners = """  // Language Tab Toggles
  const langTabs = document.querySelectorAll('.pt-lang-btn');
  langTabs.forEach(btn => {
    btn.onclick = function() {
      langTabs.forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      activeLang = this.getAttribute('data-lang');
      const lines = (activeLang === 'cpp' && model.code_cpp) ? model.code_cpp : 
                    (activeLang === 'java' && model.code_java) ? model.code_java : 
                    model.code;
      if (activeFunc && lines.length > 0) {
        activeFunc.textContent = lines[0].replace(/\\s*\\{.*$/, '');
      }
      render();
    };
  });

  btnFirst.onclick = function() {"""

updated_template = updated_template.replace(old_listeners, new_listeners)

# Write output to pattern.html
patterns_json = json.dumps(PATTERNS, indent=2)
full_html = updated_template.replace("__PATTERNS_JSON__", patterns_json)
target_path = Path("src/trackboard/templates/pages/pattern.html")
target_path.write_text(full_html)
print(f"✓ Successfully generated pattern.html ({len(full_html)} bytes) with Python, C++, and Java support!")
