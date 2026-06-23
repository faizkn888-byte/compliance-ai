"use client";
import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./context/AuthContext";
import { useDropzone } from "react-dropzone";
import { Upload, FileText, Shield, CheckCircle, AlertTriangle, AlertCircle, Clock, Loader2, Download, Wand2, LogOut, User as UserIcon } from "lucide-react";
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
}

interface UploadResponse {
  id: string | number;
  name: string;
}

interface GenerateFixResponse {
  fixed_policy: string;
}

export default function Home() {
  const { user, token, logout, isLoading: authLoading } = useAuth();
  const router = useRouter();
  
  const [documents, setDocuments] = useState<ComplianceDocument[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [generatedDoc, setGeneratedDoc] = useState<string | null>(null);

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

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
    }
  }, [authLoading, user, router]);

  useEffect(() => {
    if (token) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      fetchDocuments();
    }
  }, [fetchDocuments, token]);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (!token) return;
    const file = acceptedFiles[0];
    const formData = new FormData();
    formData.append("file", file);

    try {
      const uploadRes = await fetch(`${API_BASE}/documents/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
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

      const analyzeRes = await fetch(`${API_BASE}/compliance/analyze/${uploadData.id}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
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
  }, [token]);

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
  const analysisGaps = analysis?.gaps ?? [];
  const analysisPassed = analysis?.passed ?? [];

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
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
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
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column */}
          <div className="lg:col-span-1 space-y-6">
            <div className="bg-white rounded-lg border shadow-sm p-6">
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
          </div>

          {/* Right Column */}
          <div className="lg:col-span-2 space-y-6">
            {isAnalyzing ? (
              <div className="bg-white rounded-lg border shadow-sm p-12 flex flex-col items-center justify-center">
                <Loader2 className="h-12 w-12 text-blue-600 animate-spin mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-1">Analyzing your document...</h3>
                <p className="text-sm text-gray-500">Checking DPDP Act 2023 compliance</p>
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
