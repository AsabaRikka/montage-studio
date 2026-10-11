"""Rule validation and constrained unique pairing, independent of any LLM."""
from __future__ import annotations
import random
import re
from collections import deque, Counter


class PlanError(ValueError):
    pass


class Flow:
    def __init__(self, n):
        self.graph = [[] for _ in range(n)]

    def edge(self, u, v, capacity):
        a = [v, capacity, None, capacity]
        b = [u, 0, a, 0]
        a[2] = b
        self.graph[u].append(a)
        self.graph[v].append(b)
        return a

    def run(self, source, sink):
        total = 0
        while True:
            levels = [-1] * len(self.graph)
            levels[source] = 0
            queue = deque([source])
            while queue:
                u = queue.popleft()
                for v, cap, _, _ in self.graph[u]:
                    if cap and levels[v] < 0:
                        levels[v] = levels[u] + 1
                        queue.append(v)
            if levels[sink] < 0:
                return total
            positions = [0] * len(levels)

            def push(u, limit):
                if u == sink:
                    return limit
                while positions[u] < len(self.graph[u]):
                    edge = self.graph[u][positions[u]]
                    if edge[1] and levels[edge[0]] == levels[u] + 1:
                        sent = push(edge[0], min(limit, edge[1]))
                        if sent:
                            edge[1] -= sent
                            edge[2][1] += sent
                            return sent
                    positions[u] += 1
                return 0
            while sent := push(source, 10**9):
                total += sent


def make_plan(intros, mains, count, mode='balanced', fixed=None, excluded=(), seed=42):
    if not intros or not mains:
        raise PlanError('请导入前贴和主视频。')
    if len(set(intros)) != len(intros) or len(set(mains)) != len(mains):
        raise PlanError('相同内容的素材只能在同一列表中出现一次。')
    if type(count) is not int or count <= 0 or count > 100000:
        raise PlanError('输出数量须为1～100000的整数。')
    if mode not in ('balanced', 'random'):
        raise PlanError('未知分配方式。')
    fixed = fixed or {}
    if any(a not in intros or type(n) is not int or n < 0 for a, n in fixed.items()):
        raise PlanError('指定次数包含未知前贴或非负整数之外的值。')
    if sum(fixed.values()) > count:
        raise PlanError('指定使用次数之和超过输出数量。')
    banned = set(map(tuple, excluded))
    available = [(a, b) for a in intros for b in mains if (a, b) not in banned]
    if count > len(available):
        raise PlanError(f'排除历史及其他任务后只有{len(available)}个可用配对，无法生成{count}条。')
    degrees = Counter(a for a, _ in available)
    for a, n in fixed.items():
        if n > degrees[a]:
            raise PlanError(f'前贴{intros.index(a)+1:02}只有{degrees[a]}个可用主视频，不能使用{n}次。')
    unknown = [a for a in intros if a not in fixed]
    remaining = count - sum(fixed.values())
    if not unknown and remaining:
        raise PlanError('所有前贴均指定次数，但合计与输出数量不符。')
    rng = random.Random(seed)
    rng.shuffle(available)
    if mode == 'random':
        result = []
        for a, n in fixed.items():
            result.extend(rng.sample([(x, b) for x, b in available if x == a], n))
        pool = [(a, b) for a, b in available if a not in fixed]
        if remaining > len(pool):
            raise PlanError('未指定次数的前贴可用配对不足。')
        result.extend(rng.sample(pool, remaining))
    else:
        # Lower-bound circulation enforces fixed A counts and balanced B counts.
        # The solver chooses where the remainders go, so history constraints can
        # change that choice without silently changing any allocation promise.
        ia = {a: i+1 for i, a in enumerate(intros)}
        ib = {b: i+1+len(intros) for i, b in enumerate(mains)}
        sink = len(intros)+len(mains)+1
        ss, tt = sink+1, sink+2
        flow = Flow(tt+1)
        demands = [0] * (tt+1)

        def bounded(u, v, lo, hi):
            demands[u] -= lo
            demands[v] += lo
            return flow.edge(u, v, hi-lo)
        base, rem = divmod(remaining, len(unknown)) if unknown else (0, 0)
        for a in intros:
            lo = fixed.get(a, base)
            hi = lo if a in fixed else base + bool(rem)
            bounded(0, ia[a], lo, hi)
        edges = [(a, b, bounded(ia[a], ib[b], 0, 1)) for a, b in available]
        base_b, rem_b = divmod(count, len(mains))
        for b in mains:
            bounded(ib[b], sink, base_b, base_b+bool(rem_b))
        bounded(sink, 0, count, count)
        required = 0
        for node, demand in enumerate(demands[:sink+1]):
            if demand > 0:
                flow.edge(ss, node, demand)
                required += demand
            elif demand < 0:
                flow.edge(node, tt, -demand)
        if flow.run(ss, tt) != required:
            raise PlanError('历史排除或指定次数使严格均匀规则无法满足。请降低数量、调整指定次数，或选择随机分配；软件未生成重复配对。')
        result = [(a, b) for a, b, edge in edges if edge[3]-edge[1] == 1]
    rng.shuffle(result)
    if len(result) != count or len(set(result)) != count or set(result) & banned:
        raise RuntimeError('配对检查异常，已阻止任务创建。')
    return result


def parse_instruction(text, intro_count):
    text = text.strip()
    if not text:
        raise PlanError('请输入组合要求。')
    if re.search(r'允许重复|可以重复|取消去重|不要去重', text):
        raise PlanError('本工具始终排除历史和重复配对，不能执行允许重复的要求。')
    if re.search(r'不要均匀|不均匀|不要平均|不随机|不要随机', text):
        raise PlanError('请明确选择“随机分配”或“均匀分配”，不要使用否定描述。')
    if ('均匀' in text or '平均' in text) and '随机' in text:
        raise PlanError('随机与严格均匀是两种分配方式，请只选一种。')
    matches = list(re.finditer(r'(?:生成|输出|制作|做|组合)\s*(\d+)\s*(?:条|个|支)', text))
    if len(matches)>1:
        raise PlanError('请只指定一次成片总数量。')
    match = matches[0] if matches else None
    if not match:
        match = re.search(r'(\d+)\s*(?:条|个|支)(?:成片|视频)', text)
    if not match:
        raise PlanError('没有明确的成片数量。示例：生成1000条，均匀分配，前贴01用200次。')
    if not 1<=int(match.group(1))<=100000:
        raise PlanError('成片数量须为1～100000。')
    fixed = {}
    fixed_pattern=r'(?:前贴|A)\s*0*(\d+)\s*(?:指定|固定|使用|用|分配)?\s*(\d+)\s*次'
    for m in re.finditer(fixed_pattern, text, re.I):
        index, n = map(int, m.groups())
        if not 1 <= index <= intro_count:
            raise PlanError(f'前贴{index}不存在。')
        if str(index-1) in fixed:
            raise PlanError(f'前贴{index}重复指定次数，请保留一条。')
        fixed[str(index-1)] = n
    remainder=text[:match.start()]+text[match.end():]
    remainder=re.sub(fixed_pattern,'',remainder,flags=re.I)
    remainder=re.sub(r'严格均匀分配|均匀分配|平均分配|随机分配|均匀|平均|随机|不重复配对|不重复|排除历史配对|避开历史配对|排除历史|避开历史|成片|视频|请|帮我|并且|以及|同时|分别|和|与|，|。|、|；|,|;|\s','',remainder)
    if remainder:
        raise PlanError('离线解析没有理解这部分要求：'+remainder[:80]+'。请使用数量/均匀/随机/前贴次数表单，或配置AI接口；未忽略该要求。')
    return dict(count=int(match.group(1)), mode='balanced' if '均匀' in text or '平均' in text else 'random', fixed=fixed)
