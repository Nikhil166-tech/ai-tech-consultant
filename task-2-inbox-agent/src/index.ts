import dotenv from "dotenv";
dotenv.config();

import { InboxService } from "./inbox_service.js";
import { createServer } from "./api/server.js";

const port = process.env.PORT || 8001;
const service = new InboxService();
const app = createServer(service);

app.listen(port, () => {
  console.log(`[Inbox Agent] Task 2 running on http://localhost:${port}`);
  console.log(`[Inbox Agent] HITL Review dashboard at http://localhost:${port}/review`);
});
