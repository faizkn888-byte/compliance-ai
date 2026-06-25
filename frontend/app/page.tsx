"use client";
import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./context/AuthContext";
import { useDropzone } from "react-dropzone";
import {
  Upload, FileText, Shield, CheckCircle, AlertTriangle, AlertCircle, Clock, Loader2,
  Download, Wand2, LogOut, User as UserIcon, Code, Database, Server, Terminal,
  BookOpen, RefreshCw, ChevronDown, ChevronUp, X, Lock, Globe, Copy, Check
} from "lucide-react";
import { API_BASE } from "../lib/api";

type DocumentStatus = "processing" | "completed" | "failed";

interface ComplianceDocument {
  id: string;
  name: string;
  type: "privacy_policy" | "data_agreement" | "other";
  status: DocumentStatus;
  score?: number;
  uploadedAt: string;
}

interface RawDocumentResponse {
  id: number | string;
  name: string;
  status: DocumentStatus;
  score?: number;
  uploadedAt?: string;
}

type Severity = "HIGH" | "MEDIUM" | "LOW";

interface Gap {
  regulation: string;
  section: string;
  severity: Severity;
  description: string;
  suggestion: string;
}

interface BreakdownItem {
  label: string;
  score: number;
  status: "pass" | "warning" | "fail";
}

interface Analysis {
  overall_score?: number;
  score?: number;
  status?: string;
  gaps?: Gap[];
  passed?: string[];
  breakdown?: BreakdownItem[];
  tech_stack?: TechStackItem[];
  dark_patterns?: DarkPattern[];
}

interface UploadResponse {
  id: string | number;
  name: string;
  regulation?: string;
}

interface GenerateFixResponse {
  fixed_policy: string;
}

interface Regulation {
  id: string;
  name: string;
  region: string;
  checks_count: number;
}

interface RegulationsResponse {
  regulations?: Regulation[];
}

interface TechStackItem {
  id: string; name: string; category: string; confidence: number;
  matched_keywords: string[]; data_types: string[];
  third_party: boolean; cross_border: boolean;
}

interface DarkPattern {
  pattern: string; severity: string; regulation: string; fix: string;
}

interface ConsentSpec {
  regulation: string; regulation_name: string; consent_model: string;
  banner_html: string; checkbox_html: string; js_implementation: string;
  purposes: Array<{id: string; label: string; description: string; third_party: string; cross_border: boolean; default_checked: boolean; required: boolean}>;
  consent_required_tech: Array<{name: string; reason: string}>;
  consent_not_required_tech: Array<{name: string; reason: string}>;
  dark_pattern_violations: string[]; must_implement: string[];
}

interface RetentionSchedule {
  data_type: string; contains_pii: boolean; pii_types: string[];
  legal_basis: string; max_retention: number | string;
  justification: string; implementation: Record<string, string>;
  anonymization_required: boolean; anonymization_method: string;
}

interface RetentionPolicy {
  regulation: string; regulation_name: string; generated_at: string;
  schedules: RetentionSchedule[];
  summary: { total_schedules: number; pii_schedules: number; require_anonymization: number; cloud_providers_detected: string[] };
}

interface ImplementationGuide {
  document_id: number; regulation: string; generated_at: string;
  tech_stack: TechStackItem[]; consent_spec: ConsentSpec;
  retention_policy: RetentionPolicy; privacy_policy: string;
  dark_patterns: DarkPattern[];
  summary: { technologies_detected: number; third_party_services: number; cross_border_services: number; consent_required_count: number };
}

export default function Home() {
  const { user, token, logout, isLoading: authLoading } = useAuth();
  const router = useRouter();

  const [documents, setDocuments] = useState<ComplianceDocument[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [generatedDoc, setGeneratedDoc] = useState<string | null>(null);
  const [selectedRegulation, setSelectedRegulation] = useState("dpdp");
  const [regulations, setRegulations] = useState<Regulation[]>([]);

  // Implementation guide state
  const [implementationGuide, setImplementationGuide] = useState<ImplementationGuide | null>(null);
  const [isLoadingImplementation, setIsLoadingImplementation] = useState(false);
  const [activeImplementationTab, setActiveImplementationTab] = useState<"consent" | "retention" | "policy" | "dark_patterns">("consent");
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const [expandedRetention, setExpandedRetention] = useState<string | null>(null);
  const [showBusinessForm, setShowBusinessForm] = useState(false);
  const [businessInfo, setBusinessInfo] = useState({
    company_name: "", website_url: "", contact_email: "", company_address: "",
  });

  const fetchDocuments = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/documents`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data: RawDocumentResponse[] = await res.json();
        const formatted: ComplianceDocument[] = data.map((d) => ({
          id: String(d.id),
          name: d.name,
          type: "other",
          status: d.status,
          score: d.score,
          uploadedAt: d.uploadedAt ? d.uploadedAt.split("T")[0] : "2024-01-01",
        }));
        setDocuments(formatted);
        if (formatted.length > 0 && !selectedDoc) {
          setSelectedDoc(String(formatted[0].id));
        }
      }
    } catch (error) {
      console.error("Failed to fetch documents:", error);
    }
  }, [selectedDoc, token]);

  const fetchRegulations = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/regulations`);
      if (!res.ok) return;
      const data: RegulationsResponse = await res.json();
      setRegulations(data.regulations ?? []);
    } catch (error) {
      console.error("Failed to fetch regulations:", error);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
    }
  }, [authLoading, user, router]);

  useEffect(() => {
    if (token) {
      fetchDocuments();
    }
  }, [fetchDocuments, token]);

  useEffect(() => {
    if (token) {
      fetchRegulations();
    }
  }, [fetchRegulations, token]);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (!token) return;
    const file = acceptedFiles[0];
    const formData = new FormData();
    formData.append("file", file);

    try {
      const uploadRes = await fetch(
        `${API_BASE}/documents/upload?regulation=${encodeURIComponent(selectedRegulation)}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        }
      );
      const uploadData: UploadResponse = await uploadRes.json();

      const newDocId = "doc-" + Date.now();
      const newDoc = {
        id: newDocId,
        name: file.name,
        type: "other" as const,
        status: "processing" as const,
        uploadedAt: new Date().toISOString().split("T")[0],
      };

      setDocuments((prev) => [newDoc, ...prev]);
      setSelectedDoc(newDocId);
      setIsAnalyzing(true);
      setAnalysis(null);
      setGeneratedDoc(null);
      setImplementationGuide(null);

      const analyzeRes = await fetch(
        `${API_BASE}/compliance/analyze/${uploadData.id}?regulation=${encodeURIComponent(selectedRegulation)}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      const analyzeData: Analysis = await analyzeRes.json();

      setDocuments((prev) => prev.map((d) =>
        d.id === newDocId
          ? { ...d, id: String(uploadData.id), status: "completed" as const, score: analyzeData.score || analyzeData.overall_score || 72 }
          : d
      ));

      setSelectedDoc(String(uploadData.id));
      setAnalysis(analyzeData);
      setIsAnalyzing(false);

    } catch (error) {
      console.error("Upload failed:", error);
      setIsAnalyzing(false);
      alert("Upload failed.");
    }
  }, [selectedRegulation, token]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/plain': ['.txt'],
    },
    maxFiles: 1,
  });

  const selectedDocument = documents.find((d) => String(d.id) === String(selectedDoc));
  const selectedRegulationDetails = regulations.find((regulation) => regulation.id === selectedRegulation);
  const analysisGaps = analysis?.gaps ?? [];
  const analysisPassed = analysis?.passed ?? [];
  const techStack = analysis?.tech_stack ?? implementationGuide?.tech_stack ?? [];
  const darkPatterns = analysis?.dark_patterns ?? implementationGuide?.dark_patterns ?? [];

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "processing":
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
      default:
        return <Clock className="h-4 w-4 text-gray-400" />;
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 80) return "text-green-600";
    if (score >= 60) return "text-yellow-600";
    return "text-red-600";
  };

  const selectedScore = selectedDocument?.score ?? 0;
  const currentScore = analysis?.overall_score ?? analysis?.score ?? selectedScore;
  const currentStatus = analysis?.status || (selectedScore >= 80 ? "Compliant" : selectedScore >= 60 ? "Needs Improvement" : "Non-Compliant");

  const handleGenerateFix = async () => {
    if (!selectedDoc || !token) return;
    setIsAnalyzing(true);
    try {
      const res = await fetch(`${API_BASE}/compliance/generate-fix/${selectedDoc}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data: GenerateFixResponse = await res.json();
      setGeneratedDoc(data.fixed_policy);
      setIsAnalyzing(false);
    } catch (error) {
      console.error("Generate fix failed:", error);
      setIsAnalyzing(false);
    }
  };

  const handleDownloadReport = async () => {
    if (!selectedDoc || !token) return;
    try {
      const res = await fetch(`${API_BASE}/compliance/report/${selectedDoc}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "compliance-report.pdf";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Report download failed:", error);
    }
  };

  const handleDownloadFix = () => {
    if (!generatedDoc) return;
    const blob = new Blob([generatedDoc], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "fixed-privacy-policy.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const fetchImplementationGuide = useCallback(async () => {
    if (!selectedDoc || !token) return;
    setIsLoadingImplementation(true);
    try {
      const formData = new URLSearchParams();
      formData.append("company_name", businessInfo.company_name || "[Your Company]");
      formData.append("website_url", businessInfo.website_url || "[your-website.com]");
      formData.append("contact_email", businessInfo.contact_email || "[privacy@company.com]");
      formData.append("company_address", businessInfo.company_address || "[Your Address]");
      const res = await fetch(
        `${API_BASE}/compliance/full-implementation/${selectedDoc}?regulation=${encodeURIComponent(selectedRegulation)}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/x-www-form-urlencoded" },
          body: formData.toString(),
        }
      );
      if (!res.ok) throw new Error("Failed to fetch implementation guide");
      const data: ImplementationGuide = await res.json();
      setImplementationGuide(data);
      setShowBusinessForm(false);
    } catch (error) { console.error("Implementation guide failed:", error); }
    finally { setIsLoadingImplementation(false); }
  }, [selectedDoc, token, selectedRegulation, businessInfo]);

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopiedCode(label);
    setTimeout(() => setCopiedCode(null), 2000);
  };

  const handleDownloadPolicy = () => {
    if (!implementationGuide?.privacy_policy) return;
    const blob = new Blob([implementationGuide.privacy_policy], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `privacy-policy-${selectedRegulation}.md`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 text-blue-600 animate-spin" />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="h-6 w-6 text-blue-600" />
            <h1 className="text-xl font-bold text-gray-900">Compliance AI</h1>
            <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">DPDP Act 2023</span>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <UserIcon className="h-4 w-4" />
              {user.full_name || user.email}
            </div>
            <button
              onClick={logout}
              className="text-sm text-gray-600 hover:text-red-600 flex items-center gap-1"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-lg border shadow-sm p-6">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-gray-500">Documents Analyzed</p>
              <FileText className="h-4 w-4 text-blue-600" />
            </div>
            <p className="text-2xl font-bold">{documents.length}</p>
          </div>
          <div className="bg-white rounded-lg border shadow-sm p-6">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-gray-500">Avg. Compliance Score</p>
              <Shield className="h-4 w-4 text-green-600" />
            </div>
            <p className="text-2xl font-bold">
              {documents.length > 0
                ? Math.round(documents.reduce((a, d) => a + (d.score || 0), 0) / documents.length)
                : 0}%
            </p>
          </div>
          <div className="bg-white rounded-lg border shadow-sm p-6">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-gray-500">Gaps Found</p>
              <AlertTriangle className="h-4 w-4 text-orange-600" />
            </div>
            <p className="text-2xl font-bold">{analysisGaps.length}</p>
          </div>
          <div className="bg-white rounded-lg border shadow-sm p-6">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-gray-500">Tech Stack Detected</p>
              <Server className="h-4 w-4 text-purple-600" />
            </div>
            <p className="text-2xl font-bold">{techStack.length}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column */}
          <div className="lg:col-span-1 space-y-6">
            <div className="bg-white rounded-lg border shadow-sm p-6">
              <div className="mb-4">
                <label htmlFor="regulation" className="block text-sm font-medium text-gray-700 mb-1">
                  Regulation
                </label>
                <select
                  id="regulation"
                  value={selectedRegulation}
                  onChange={(e) => {
                    setSelectedRegulation(e.target.value);
                    setImplementationGuide(null);
                  }}
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {regulations.length === 0 ? (
                    <option value="dpdp">DPDP Act 2023</option>
                  ) : (
                    regulations.map((regulation) => (
                      <option key={regulation.id} value={regulation.id}>
                        {regulation.name} - {regulation.region} ({regulation.checks_count} checks)
                      </option>
                    ))
                  )}
                </select>
              </div>

              <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                  isDragActive ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400"
                }`}
              >
                <input {...getInputProps()} />
                <Upload className="h-10 w-10 text-gray-400 mx-auto mb-4" />
                {isDragActive ? (
                  <p className="text-blue-600 font-medium">Drop the file here...</p>
                ) : (
                  <>
                    <p className="text-gray-700 font-medium mb-1">Drag & drop your document</p>
                    <p className="text-sm text-gray-500">or click to browse (PDF, DOCX, TXT)</p>
                  </>
                )}
              </div>
            </div>

            <div className="bg-white rounded-lg border shadow-sm">
              <div className="p-4 border-b">
                <h3 className="font-medium text-gray-900">Recent Documents</h3>
              </div>
              <div className="divide-y">
                {documents.length === 0 && (
                  <div className="p-4 text-center text-sm text-gray-500">
                    No documents yet. Upload one to get started.
                  </div>
                )}
                {documents.map((doc) => (
                  <button
                    key={doc.id}
                    onClick={() => {
                      setSelectedDoc(doc.id);
                      setAnalysis(null);
                      setGeneratedDoc(null);
                      setImplementationGuide(null);
                    }}
                    className={`w-full flex items-center gap-3 p-4 text-left transition-colors ${
                      String(selectedDoc) === String(doc.id) ? "bg-blue-50" : "hover:bg-gray-50"
                    }`}
                  >
                    <FileText className="h-5 w-5 text-gray-400 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{doc.name}</p>
                      <p className="text-xs text-gray-500 capitalize">{doc.type.replace("_", " ")}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {doc.score !== undefined && doc.status === "completed" && (
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                          doc.score >= 80 ? "bg-green-100 text-green-700" :
                          doc.score >= 60 ? "bg-yellow-100 text-yellow-700" :
                          "bg-red-100 text-red-700"
                        }`}>
                          {doc.score}%
                        </span>
                      )}
                      {getStatusIcon(doc.status)}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Tech Stack Card */}
            {techStack.length > 0 && (
              <div className="bg-white rounded-lg border shadow-sm p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Server className="h-5 w-5 text-purple-600" />
                  <h3 className="font-medium text-gray-900">Detected Tech Stack</h3>
                </div>
                <div className="space-y-2">
                  {techStack.slice(0, 6).map((tech, i) => (
                    <div key={i} className="flex items-center justify-between p-2 bg-gray-50 rounded-md">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${tech.third_party ? 'bg-orange-400' : 'bg-green-400'}`} />
                        <span className="text-sm font-medium text-gray-700">{tech.name}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {tech.cross_border && <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">Cross-border</span>}
                        <span className="text-xs text-gray-500">{tech.confidence.toFixed(0)}%</span>
                      </div>
                    </div>
                  ))}
                </div>
                {techStack.length > 6 && <p className="text-xs text-gray-500 mt-2 text-center">+{techStack.length - 6} more detected</p>}
              </div>
            )}

            {/* Dark Patterns Alert */}
            {darkPatterns.length > 0 && (
              <div className="bg-white rounded-lg border border-red-200 shadow-sm p-6">
                <div className="flex items-center gap-2 mb-4">
                  <AlertCircle className="h-5 w-5 text-red-600" />
                  <h3 className="font-medium text-gray-900">Dark Pattern Alerts</h3>
                </div>
                <div className="space-y-2">
                  {darkPatterns.slice(0, 3).map((dp, i) => (
                    <div key={i} className="p-2 bg-red-50 rounded-md border border-red-100">
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${dp.severity === 'HIGH' ? 'bg-red-200 text-red-800' : 'bg-yellow-200 text-yellow-800'}`}>{dp.severity}</span>
                        <span className="text-sm text-gray-800">{dp.pattern}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right Column */}
          <div className="lg:col-span-2 space-y-6">
            {isAnalyzing ? (
              <div className="bg-white rounded-lg border shadow-sm p-12 flex flex-col items-center justify-center">
                <Loader2 className="h-12 w-12 text-blue-600 animate-spin mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-1">Analyzing your document...</h3>
                <p className="text-sm text-gray-500">
                  Checking {selectedRegulationDetails?.name ?? "selected regulation"} compliance
                </p>
              </div>
            ) : selectedDocument ? (
              <>
                <div className="bg-white rounded-lg border shadow-sm p-6">
                  <h2 className="flex items-center gap-2 font-medium text-gray-900 mb-6">
                    <Shield className="h-5 w-5 text-blue-600" />
                    Compliance Score
                  </h2>

                  <div className="flex items-center gap-6 mb-8">
                    <div className="relative w-24 h-24">
                      <svg className="w-24 h-24 transform -rotate-90">
                        <circle cx="48" cy="48" r="40" stroke="currentColor" strokeWidth="8" fill="transparent" className="text-gray-200" />
                        <circle cx="48" cy="48" r="40" stroke="currentColor" strokeWidth="8" fill="transparent"
                          strokeDasharray={`${(currentScore / 100) * 251.2} 251.2`}
                          className={getScoreColor(currentScore)}
                        />
                      </svg>
                      <div className="absolute inset-0 flex items-center justify-center">
                        <span className={`text-2xl font-bold ${getScoreColor(currentScore)}`}>
                          {currentScore}%
                        </span>
                      </div>
                    </div>
                    <div>
                      <h3 className="text-lg font-medium text-gray-900">{currentStatus}</h3>
                      <p className="text-sm text-gray-500">
                        {analysisGaps.length > 0
                          ? `${analysisGaps.length} gaps found`
                          : analysisPassed.length > 0
                          ? `${analysisPassed.length} checks passed`
                          : "Analysis complete"}
                      </p>
                    </div>
                  </div>

                  {analysis?.breakdown && (
                    <div className="space-y-3">
                      {analysis.breakdown.map((item, index) => (
                        <div key={index} className="space-y-1">
                          <div className="flex items-center justify-between text-sm">
                            <span className="flex items-center gap-2">
                              {item.status === "pass" ? <CheckCircle className="h-4 w-4 text-green-500" /> :
                               item.status === "warning" ? <AlertTriangle className="h-4 w-4 text-yellow-500" /> :
                               <AlertCircle className="h-4 w-4 text-red-500" />}
                              {item.label}
                            </span>
                            <span className="font-medium">{item.score}%</span>
                          </div>
                          <div className="w-full bg-gray-200 rounded-full h-2">
                            <div className={`h-2 rounded-full ${
                              item.score >= 80 ? "bg-green-600" :
                              item.score >= 60 ? "bg-yellow-600" :
                              "bg-red-600"
                            }`} style={{ width: `${item.score}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Implementation Guide Panel */}
                {analysis && (
                  <div className="bg-white rounded-lg border shadow-sm overflow-hidden">
                    {/* Header */}
                    <div className="p-6 border-b bg-gradient-to-r from-blue-50 to-purple-50">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="p-2 bg-blue-100 rounded-lg">
                            <Wand2 className="h-5 w-5 text-blue-700" />
                          </div>
                          <div>
                            <h2 className="text-lg font-semibold text-gray-900">Actionable Implementation Guide</h2>
                            <p className="text-sm text-gray-600">
                              Exact code, retention schedules, and boilerplate for your {selectedRegulation.toUpperCase()} compliance
                            </p>
                          </div>
                        </div>
                        <button
                          onClick={() => {
                            if (!showBusinessForm && !implementationGuide) { setShowBusinessForm(true); }
                            else if (implementationGuide) { setImplementationGuide(null); setShowBusinessForm(true); }
                            else { fetchImplementationGuide(); }
                          }}
                          disabled={isLoadingImplementation}
                          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 flex items-center gap-2 disabled:opacity-50 text-sm font-medium"
                        >
                          {isLoadingImplementation ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : implementationGuide ? (
                            <><RefreshCw className="h-4 w-4" /> Regenerate</>
                          ) : (
                            <><Wand2 className="h-4 w-4" /> Generate Guide</>
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Business Info Form */}
                    {showBusinessForm && !implementationGuide && (
                      <div className="p-6 border-b bg-gray-50">
                        <h3 className="text-sm font-semibold text-gray-700 mb-4">Business Information (for tailored policy)</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Company Name</label>
                            <input type="text" value={businessInfo.company_name}
                              onChange={(e) => setBusinessInfo({...businessInfo, company_name: e.target.value})}
                              placeholder="Acme Inc." className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500" />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Website URL</label>
                            <input type="text" value={businessInfo.website_url}
                              onChange={(e) => setBusinessInfo({...businessInfo, website_url: e.target.value})}
                              placeholder="acme.com" className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500" />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Privacy Email</label>
                            <input type="email" value={businessInfo.contact_email}
                              onChange={(e) => setBusinessInfo({...businessInfo, contact_email: e.target.value})}
                              placeholder="privacy@acme.com" className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500" />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Company Address</label>
                            <input type="text" value={businessInfo.company_address}
                              onChange={(e) => setBusinessInfo({...businessInfo, company_address: e.target.value})}
                              placeholder="Mumbai, India" className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500" />
                          </div>
                        </div>
                        <button onClick={fetchImplementationGuide} disabled={isLoadingImplementation}
                          className="mt-4 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 text-sm font-medium disabled:opacity-50">
                          {isLoadingImplementation ? "Generating..." : "Generate Implementation Guide"}
                        </button>
                      </div>
                    )}

                    {/* Implementation Content */}
                    {implementationGuide && (
                      <div>
                        {/* Summary Bar */}
                        <div className="p-4 bg-gray-50 border-b grid grid-cols-2 md:grid-cols-4 gap-4">
                          <div className="text-center">
                            <p className="text-2xl font-bold text-purple-600">{implementationGuide.summary.technologies_detected}</p>
                            <p className="text-xs text-gray-500">Technologies</p>
                          </div>
                          <div className="text-center">
                            <p className="text-2xl font-bold text-orange-600">{implementationGuide.summary.third_party_services}</p>
                            <p className="text-xs text-gray-500">Third-Party</p>
                          </div>
                          <div className="text-center">
                            <p className="text-2xl font-bold text-red-600">{implementationGuide.summary.cross_border_services}</p>
                            <p className="text-xs text-gray-500">Cross-Border</p>
                          </div>
                          <div className="text-center">
                            <p className="text-2xl font-bold text-blue-600">{implementationGuide.summary.consent_required_count}</p>
                            <p className="text-xs text-gray-500">Need Consent</p>
                          </div>
                        </div>

                        {/* Tabs */}
                        <div className="flex border-b">
                          {[
                            { id: "consent" as const, label: "Consent UI", icon: Code },
                            { id: "retention" as const, label: "Data Retention", icon: Database },
                            { id: "policy" as const, label: "Privacy Policy", icon: BookOpen },
                            { id: "dark_patterns" as const, label: "Dark Patterns", icon: AlertTriangle },
                          ].map((tab) => (
                            <button key={tab.id} onClick={() => setActiveImplementationTab(tab.id)}
                              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                                activeImplementationTab === tab.id
                                  ? "border-blue-600 text-blue-600 bg-blue-50"
                                  : "border-transparent text-gray-600 hover:text-gray-900 hover:bg-gray-50"
                              }`}>
                              <tab.icon className="h-4 w-4" /> {tab.label}
                            </button>
                          ))}
                        </div>

                        {/* Tab Content */}
                        <div className="p-6">
                          {/* CONSENT TAB */}
                          {activeImplementationTab === "consent" && implementationGuide.consent_spec && (
                            <div className="space-y-6">
                              <div className="flex items-center justify-between">
                                <div>
                                  <h3 className="text-lg font-semibold text-gray-900">{implementationGuide.consent_spec.regulation_name} Consent Specification</h3>
                                  <p className="text-sm text-gray-500">Model: <span className="font-medium text-blue-600">{implementationGuide.consent_spec.consent_model}</span></p>
                                </div>
                                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full font-medium">Copy-paste ready</span>
                              </div>

                              {/* Must Implement */}
                              <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                                <h4 className="text-sm font-semibold text-amber-800 mb-2 flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Mandatory Requirements</h4>
                                <ul className="space-y-1">
                                  {implementationGuide.consent_spec.must_implement.map((item, i) => (
                                    <li key={i} className="text-sm text-amber-700 flex items-start gap-2"><CheckCircle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />{item}</li>
                                  ))}
                                </ul>
                              </div>

                              {/* Consent Required Tech */}
                              {implementationGuide.consent_spec.consent_required_tech.length > 0 && (
                                <div>
                                  <h4 className="text-sm font-semibold text-gray-700 mb-2">Services Requiring Explicit Consent</h4>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                    {implementationGuide.consent_spec.consent_required_tech.map((tech, i) => (
                                      <div key={i} className="flex items-center gap-2 p-2 bg-red-50 border border-red-100 rounded-md">
                                        <Lock className="h-4 w-4 text-red-500" />
                                        <div><p className="text-sm font-medium text-gray-800">{tech.name}</p><p className="text-xs text-gray-500">{tech.reason}</p></div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Code Sections */}
                              <div className="space-y-4">
                                {[
                                  { label: "Consent Banner HTML", code: implementationGuide.consent_spec.banner_html, copyKey: "banner", icon: Globe },
                                  { label: "Checkbox HTML", code: implementationGuide.consent_spec.checkbox_html, copyKey: "checkbox", icon: CheckCircle },
                                  { label: "JavaScript Implementation", code: implementationGuide.consent_spec.js_implementation, copyKey: "js", icon: Terminal },
                                ].map((section) => (
                                  <div key={section.copyKey}>
                                    <div className="flex items-center justify-between mb-2">
                                      <h4 className="text-sm font-semibold text-gray-700 flex items-center gap-2"><section.icon className="h-4 w-4" />{section.label}</h4>
                                      <button onClick={() => copyToClipboard(section.code, section.copyKey)}
                                        className="text-xs bg-gray-100 hover:bg-gray-200 px-2 py-1 rounded flex items-center gap-1">
                                        {copiedCode === section.copyKey ? <><Check className="h-3 w-3 text-green-600" />Copied</> : <><Copy className="h-3 w-3" />Copy</>}
                                      </button>
                                    </div>
                                    <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg text-xs overflow-x-auto max-h-64 overflow-y-auto"><code>{section.code}</code></pre>
                                  </div>
                                ))}
                              </div>

                              {/* Dark Pattern Violations */}
                              {implementationGuide.consent_spec.dark_pattern_violations.length > 0 && (
                                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                                  <h4 className="text-sm font-semibold text-red-800 mb-2">Forbidden Patterns (Will Fail Audit)</h4>
                                  <ul className="space-y-1">
                                    {implementationGuide.consent_spec.dark_pattern_violations.map((item, i) => (
                                      <li key={i} className="text-sm text-red-700 flex items-start gap-2"><X className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />{item}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          )}

                          {/* RETENTION TAB */}
                          {activeImplementationTab === "retention" && implementationGuide.retention_policy && (
                            <div className="space-y-6">
                              <div className="flex items-center justify-between">
                                <div>
                                  <h3 className="text-lg font-semibold text-gray-900">Data Retention Schedule</h3>
                                  <p className="text-sm text-gray-500">{implementationGuide.retention_policy.regulation_name} — {implementationGuide.retention_policy.schedules.length} schedules</p>
                                </div>
                              </div>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                <div className="bg-blue-50 p-3 rounded-lg text-center"><p className="text-xl font-bold text-blue-700">{implementationGuide.retention_policy.summary.total_schedules}</p><p className="text-xs text-blue-600">Schedules</p></div>
                                <div className="bg-orange-50 p-3 rounded-lg text-center"><p className="text-xl font-bold text-orange-700">{implementationGuide.retention_policy.summary.pii_schedules}</p><p className="text-xs text-orange-600">Contain PII</p></div>
                                <div className="bg-purple-50 p-3 rounded-lg text-center"><p className="text-xl font-bold text-purple-700">{implementationGuide.retention_policy.summary.require_anonymization}</p><p className="text-xs text-purple-600">Need Anonymization</p></div>
                                <div className="bg-green-50 p-3 rounded-lg text-center"><p className="text-xl font-bold text-green-700">{implementationGuide.retention_policy.summary.cloud_providers_detected.length}</p><p className="text-xs text-green-600">Cloud Providers</p></div>
                              </div>
                              <div className="space-y-4">
                                {implementationGuide.retention_policy.schedules.map((sched, i) => (
                                  <div key={i} className="border rounded-lg overflow-hidden">
                                    <button onClick={() => setExpandedRetention(expandedRetention === String(i) ? null : String(i))}
                                      className="w-full flex items-center justify-between p-4 bg-gray-50 hover:bg-gray-100 transition-colors">
                                      <div className="flex items-center gap-3">
                                        {sched.contains_pii ? <AlertCircle className="h-5 w-5 text-red-500" /> : <CheckCircle className="h-5 w-5 text-green-500" />}
                                        <div className="text-left">
                                          <h4 className="font-medium text-gray-900">{sched.data_type}</h4>
                                          <p className="text-xs text-gray-500">Retention: <span className="font-medium">{typeof sched.max_retention === 'number' ? `${sched.max_retention} days` : sched.max_retention}</span>{sched.anonymization_required && <span className="ml-2 text-purple-600">• Anonymization required</span>}</p>
                                        </div>
                                      </div>
                                      {expandedRetention === String(i) ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
                                    </button>
                                    {expandedRetention === String(i) && (
                                      <div className="p-4 space-y-4 bg-white">
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                          <div><p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Legal Basis</p><p className="text-sm text-gray-800">{sched.legal_basis}</p></div>
                                          <div><p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">PII Types</p><p className="text-sm text-gray-800">{sched.pii_types.join(", ")}</p></div>
                                        </div>
                                        <div className="bg-blue-50 border border-blue-100 rounded-lg p-3"><p className="text-xs font-semibold text-blue-700 mb-1">Justification</p><p className="text-sm text-blue-800">{sched.justification}</p></div>
                                        {sched.anonymization_required && (
                                          <div className="bg-purple-50 border border-purple-100 rounded-lg p-3"><p className="text-xs font-semibold text-purple-700 mb-1">Anonymization Method</p><p className="text-sm text-purple-800">{sched.anonymization_method}</p></div>
                                        )}
                                        {Object.entries(sched.implementation).length > 0 && (
                                          <div className="space-y-3">
                                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Implementation</p>
                                            {Object.entries(sched.implementation).map(([key, code]) => (
                                              <div key={key} className="relative">
                                                <div className="flex items-center justify-between mb-1">
                                                  <span className="text-xs font-medium text-gray-600 capitalize">{key.replace(/_/g, " ")}</span>
                                                  <button onClick={() => copyToClipboard(code, `retention-${i}-${key}`)} className="text-xs bg-gray-100 hover:bg-gray-200 px-2 py-0.5 rounded flex items-center gap-1">
                                                    {copiedCode === `retention-${i}-${key}` ? <Check className="h-3 w-3 text-green-600" /> : <Copy className="h-3 w-3" />}
                                                  </button>
                                                </div>
                                                <pre className="bg-gray-900 text-gray-100 p-3 rounded-lg text-xs overflow-x-auto"><code>{code}</code></pre>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* POLICY TAB */}
                          {activeImplementationTab === "policy" && implementationGuide.privacy_policy && (
                            <div className="space-y-4">
                              <div className="flex items-center justify-between">
                                <div>
                                  <h3 className="text-lg font-semibold text-gray-900">Tailored Privacy Policy</h3>
                                  <p className="text-sm text-gray-500">Assembled from {implementationGuide.tech_stack.length} tech-specific modules • {implementationGuide.privacy_policy.split(/\s+/).length} words</p>
                                </div>
                                <button onClick={handleDownloadPolicy} className="text-sm bg-green-600 text-white px-3 py-1.5 rounded-md hover:bg-green-700 flex items-center gap-1"><Download className="h-3.5 w-3.5" />Download .md</button>
                              </div>
                              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
                                <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
                                <p className="text-xs text-amber-700">This is an auto-generated template based on your detected tech stack. <strong>Replace all [bracketed placeholders]</strong> with your actual business details before use. Always review with qualified legal counsel.</p>
                              </div>
                              <div className="relative">
                                <pre className="bg-gray-50 border border-gray-200 p-6 rounded-lg text-sm text-gray-700 whitespace-pre-wrap font-mono max-h-[600px] overflow-y-auto">{implementationGuide.privacy_policy}</pre>
                              </div>
                            </div>
                          )}

                          {/* DARK PATTERNS TAB */}
                          {activeImplementationTab === "dark_patterns" && (
                            <div className="space-y-6">
                              <h3 className="text-lg font-semibold text-gray-900">Dark Pattern Detection</h3>
                              {implementationGuide.dark_patterns.length === 0 ? (
                                <div className="bg-green-50 border border-green-200 rounded-lg p-6 text-center">
                                  <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-3" />
                                  <h4 className="text-base font-medium text-green-800">No Dark Patterns Detected</h4>
                                  <p className="text-sm text-green-600 mt-1">Your document does not contain common dark pattern language. Good job!</p>
                                </div>
                              ) : (
                                <div className="space-y-4">
                                  {implementationGuide.dark_patterns.map((dp, i) => (
                                    <div key={i} className={`border rounded-lg p-4 ${dp.severity === 'HIGH' ? 'bg-red-50 border-red-200' : 'bg-yellow-50 border-yellow-200'}`}>
                                      <div className="flex items-start gap-3">
                                        <AlertTriangle className={`h-5 w-5 mt-0.5 flex-shrink-0 ${dp.severity === 'HIGH' ? 'text-red-500' : 'text-yellow-500'}`} />
                                        <div className="flex-1">
                                          <div className="flex items-center gap-2 mb-1">
                                            <h4 className="font-medium text-gray-900">{dp.pattern}</h4>
                                            <span className={`text-xs font-bold px-2 py-0.5 rounded ${dp.severity === 'HIGH' ? 'bg-red-200 text-red-800' : 'bg-yellow-200 text-yellow-800'}`}>{dp.severity}</span>
                                          </div>
                                          <p className="text-xs text-gray-500 mb-2">{dp.regulation}</p>
                                          <div className="bg-white border rounded-md p-3"><p className="text-xs font-semibold text-gray-600 mb-1">Required Fix:</p><p className="text-sm text-gray-700">{dp.fix}</p></div>
                                        </div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {analysisGaps.length > 0 && (
                  <div className="bg-white rounded-lg border shadow-sm p-6">
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="flex items-center gap-2 font-medium text-gray-900">
                        <AlertTriangle className="h-5 w-5 text-orange-600" />
                        Compliance Gaps ({analysisGaps.length})
                      </h2>
                      <div className="flex gap-2">
                        <button
                          onClick={handleGenerateFix}
                          disabled={isAnalyzing}
                          className="text-sm bg-blue-600 text-white px-3 py-1.5 rounded-md hover:bg-blue-700 flex items-center gap-1 disabled:opacity-50"
                        >
                          <Wand2 className="h-3.5 w-3.5" />
                          Generate Fix
                        </button>
                        <button
                          onClick={handleDownloadReport}
                          className="text-sm bg-purple-600 text-white px-3 py-1.5 rounded-md hover:bg-purple-700 flex items-center gap-1"
                        >
                          <Download className="h-3.5 w-3.5" />
                          Download Report
                        </button>
                      </div>
                    </div>

                    <div className="space-y-4">
                      {analysisGaps.map((gap, i) => (
                        <div key={i} className="border rounded-lg p-4 space-y-3">
                          <div className="flex items-start gap-3">
                            {gap.severity === "HIGH" ? <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" /> :
                             gap.severity === "MEDIUM" ? <AlertTriangle className="h-5 w-5 text-yellow-500 mt-0.5" /> :
                             <AlertCircle className="h-5 w-5 text-blue-500 mt-0.5" />}
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <h4 className="font-medium text-gray-900">{gap.regulation}</h4>
                                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                                  gap.severity === "HIGH" ? "bg-red-100 text-red-700" :
                                  gap.severity === "MEDIUM" ? "bg-yellow-100 text-yellow-700" :
                                  "bg-blue-100 text-blue-700"
                                }`}>
                                  {gap.severity}
                                </span>
                              </div>
                              <p className="text-sm text-gray-500">{gap.section}</p>
                            </div>
                          </div>
                          <p className="text-sm text-gray-700 pl-8">{gap.description}</p>
                          <div className="bg-blue-50 border border-blue-100 rounded-md p-3 ml-8">
                            <p className="text-sm text-blue-800">
                              <span className="font-medium">Suggestion: </span>
                              {gap.suggestion}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {analysisPassed.length > 0 && (
                  <div className="bg-white rounded-lg border shadow-sm p-6">
                    <h2 className="flex items-center gap-2 font-medium text-gray-900 mb-4">
                      <CheckCircle className="h-5 w-5 text-green-600" />
                      Passed Checks ({analysisPassed.length})
                    </h2>
                    <div className="space-y-2">
                      {analysisPassed.map((item, i) => (
                        <div key={i} className="flex items-center gap-2 text-sm text-green-700 bg-green-50 rounded-md px-3 py-2">
                          <CheckCircle className="h-4 w-4 flex-shrink-0" />
                          {item}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {generatedDoc && (
                  <div className="bg-white rounded-lg border shadow-sm p-6">
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="flex items-center gap-2 font-medium text-gray-900">
                        <Wand2 className="h-5 w-5 text-purple-600" />
                        Fixed Privacy Policy
                      </h2>
                      <button
                        onClick={handleDownloadFix}
                        className="text-sm bg-green-600 text-white px-3 py-1.5 rounded-md hover:bg-green-700 flex items-center gap-1"
                      >
                        <Download className="h-3.5 w-3.5" />
                        Download
                      </button>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-4 max-h-96 overflow-y-auto">
                      <pre className="text-sm text-gray-700 whitespace-pre-wrap font-mono">
                        {generatedDoc}
                      </pre>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="bg-white rounded-lg border shadow-sm h-96 flex items-center justify-center">
                <div className="text-center">
                  <Shield className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-1">Select a document to analyze</h3>
                  <p className="text-sm text-gray-500">Upload a privacy policy or compliance document to get started</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}