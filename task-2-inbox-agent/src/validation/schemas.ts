import { z } from "zod";

export const CustomerEmailSchema = z.object({
  id: z.string().min(1, "Email id is required"),
  senderEmail: z.string().email("Valid sender email is required"),
  senderName: z.string().optional(),
  subject: z.string().min(1, "Subject is required"),
  body: z.string(),
  receivedAt: z.string().optional().default(() => new Date().toISOString())
});

export const ReviewActionSchema = z.enum(["APPROVE", "EDIT", "REJECT"]);

export const ReviewSubmissionSchema = z.object({
  action: ReviewActionSchema,
  reviewerId: z.string().min(1, "reviewerId is required"),
  finalReply: z.string().optional(),
  notes: z.string().optional(),
  sendViaGmail: z.boolean().optional().default(false)
});

export const AutonomyRevocationSchema = z.object({
  kindKey: z.string().min(1, "kindKey is required"),
  reason: z.string().min(1, "reason is required"),
  revokedBy: z.string().optional().default("quality_auditor")
});

export const Task1CitationSchema = z.object({
  url: z.string(),
  title: z.string(),
  category: z.string().optional().default(""),
  folder: z.string().optional().default(""),
  section_heading: z.string(),
  snippet: z.string().optional().default(""),
  source_type: z.string().optional().default("OFFICIAL_DOC"),
  provenance_notes: z.string().nullable().optional()
}).passthrough();

export const Task1AskResponseSchema = z.object({
  answer: z.string().min(1, "Task 1 answer must be a non-empty string"),
  citations: z.array(Task1CitationSchema),
  evidence_score: z.number().min(0).max(1),
  evidence_status: z.enum(["STRONG", "PARTIAL", "INSUFFICIENT", "NONE"]),
  is_known: z.boolean(),
  needs_human_review: z.boolean(),
  expert_task_id: z.string().nullable().optional(),
  visual_references: z.array(z.any()).optional().default([]),
  confidence_score: z.number().optional()
}).passthrough();
