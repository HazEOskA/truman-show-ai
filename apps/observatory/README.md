# Observatory

The read-first operator view. It watches a world; it never simulates one.

```bash
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Fourteen views, one per question an operator actually asks:

| View | Question |
|---|---|
| World | what is happening right now, and what is it costing to simulate |
| Map | how does a metric spread across the districts |
| Hydra | what is the physical city made of |
| People | who lives here — and, clicking one, what do *they* know |
| Companies | which firms are healthy, which are cutting |
| Economy | what do things cost, and why |
| Governments | what has city hall decided, and on what evidence |
| Media | which outlet is telling which version |
| Technology | what is being researched, and what has spread |
| Culture | what has the city started saying |
| Events | the immutable ledger |
| Causal graph | why did this happen |
| Timeline | fork the world and run two histories |

Every page polls one projection endpoint. The only writes are the operator's own intent —
create, run, pause, step, scenario, fork — which the API records and the worker picks up at a
tick boundary. Nothing the Observatory does can reach into a running tick.
