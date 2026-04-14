import { api } from "./client";

export interface PDFReport {
  filename: string;
  date: string;
  year: number;
  month: number;
  size_bytes: number;
}

export const reportsApi = {
  list: () => api.get<PDFReport[]>("/market/reports/"),
  downloadUrl: (filename: string) => `/api/market/reports/${filename}/`,
};
