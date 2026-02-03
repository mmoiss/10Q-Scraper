"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

type FormState = "idle" | "loading" | "success" | "error";

export default function AppPage() {
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [ticker, setTicker] = useState("");
    const [bankCodes, setBankCodes] = useState("");
    const [activeTab, setActiveTab] = useState<"sec" | "fdic">("sec");
    const [formState, setFormState] = useState<FormState>("idle");
    const [errorMessage, setErrorMessage] = useState("");
    const [statusMessage, setStatusMessage] = useState("");
    const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
    const [fileName, setFileName] = useState("");
    const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
    const router = useRouter();
    const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

    // Cleanup polling on unmount
    useEffect(() => {
        return () => {
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
            }
        };
    }, []);

    // Check authentication on mount
    useEffect(() => {
        const checkAuth = async () => {
            try {
                const response = await fetch("/api/auth/check", {
                    credentials: "include",
                });
                const data = await response.json();

                if (!data.authenticated) {
                    router.push("/");
                    return;
                }
                setIsAuthenticated(true);
            } catch {
                router.push("/");
            }
        };

        checkAuth();
    }, [router]);

    const handleLogout = async () => {
        try {
            await fetch("/api/logout", {
                method: "POST",
                credentials: "include",
            });
        } catch {
            // Ignore errors
        }
        router.push("/");
    };

    const handleFdicSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormState("loading");
        setErrorMessage("");
        setStatusMessage("Starting FDIC job...");
        setDownloadUrl(null);

        try {
            const response = await fetch("/api/generate-fdic", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                credentials: "include",
                body: JSON.stringify({
                    bank_codes: bankCodes,
                }),
            });

            if (response.status === 401) {
                router.push("/");
                return;
            }

            if (!response.ok) {
                let errorMsg = "An error occurred while starting the job.";
                try {
                    const errorData = await response.json();
                    if (errorData.detail) {
                        errorMsg = Array.isArray(errorData.detail)
                            ? errorData.detail[0]?.msg || errorMsg
                            : errorData.detail;
                    }
                } catch {
                    errorMsg = `Server error: ${response.status} ${response.statusText}`;
                }
                throw new Error(errorMsg);
            }

            const data = await response.json();
            const jobId = data.job_id;
            const jobTicker = "FDIC";

            setStatusMessage("Processing FDIC data...");
            pollJobStatus(jobId, jobTicker);
            pollIntervalRef.current = setInterval(() => pollJobStatus(jobId, jobTicker), 2000);

        } catch (error) {
            setFormState("error");
            setErrorMessage(
                error instanceof Error ? error.message : "An unexpected error occurred."
            );
        }
    };

    const pollJobStatus = async (jobId: string, jobTicker: string) => {
        try {
            const response = await fetch(`/api/job/${jobId}`, {
                credentials: "include",
            });

            if (response.status === 401) {
                if (pollIntervalRef.current) {
                    clearInterval(pollIntervalRef.current);
                    pollIntervalRef.current = null;
                }
                router.push("/");
                return;
            }

            if (!response.ok) {
                throw new Error("Failed to check job status");
            }

            const data = await response.json();
            setStatusMessage(data.message || "Processing...");

            if (data.status === "completed") {
                // Stop polling
                if (pollIntervalRef.current) {
                    clearInterval(pollIntervalRef.current);
                    pollIntervalRef.current = null;
                }

                // Download the result
                const downloadResponse = await fetch(`/api/job/${jobId}/download`, {
                    credentials: "include",
                });

                if (!downloadResponse.ok) {
                    throw new Error("Failed to download result");
                }

                const blob = await downloadResponse.blob();
                const url = window.URL.createObjectURL(blob);
                setDownloadUrl(url);
                setFileName(data.filename || `${jobTicker}_Financials.xlsx`);
                setFormState("success");
                setStatusMessage("");
            } else if (data.status === "error") {
                // Stop polling
                if (pollIntervalRef.current) {
                    clearInterval(pollIntervalRef.current);
                    pollIntervalRef.current = null;
                }
                throw new Error(data.error || "An error occurred");
            }
            // If still processing, polling continues
        } catch (error) {
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
                pollIntervalRef.current = null;
            }
            setFormState("error");
            setErrorMessage(
                error instanceof Error ? error.message : "An unexpected error occurred."
            );
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormState("loading");
        setErrorMessage("");
        setStatusMessage("Starting job...");
        setDownloadUrl(null);

        try {
            // Start the background job
            const response = await fetch("/api/generate", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                credentials: "include",
                body: JSON.stringify({
                    name,
                    email,
                    ticker: ticker.toUpperCase(),
                }),
            });

            if (response.status === 401) {
                router.push("/");
                return;
            }

            if (!response.ok) {
                let errorMsg = "An error occurred while starting the job.";
                try {
                    const errorData = await response.json();
                    if (errorData.detail) {
                        errorMsg = Array.isArray(errorData.detail)
                            ? errorData.detail[0]?.msg || errorMsg
                            : errorData.detail;
                    }
                } catch {
                    errorMsg = `Server error: ${response.status} ${response.statusText}`;
                }
                throw new Error(errorMsg);
            }

            const data = await response.json();
            const jobId = data.job_id;
            const jobTicker = ticker.toUpperCase();

            // Start polling for job status - poll immediately, then every 2 seconds
            setStatusMessage("Processing SEC filings...");
            pollJobStatus(jobId, jobTicker);  // Poll immediately
            pollIntervalRef.current = setInterval(() => pollJobStatus(jobId, jobTicker), 2000);

        } catch (error) {
            setFormState("error");
            setErrorMessage(
                error instanceof Error ? error.message : "An unexpected error occurred."
            );
        }
    };

    const handleDownload = () => {
        if (downloadUrl) {
            const link = document.createElement("a");
            link.href = downloadUrl;
            link.download = fileName;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    };

    const handleReset = () => {
        setFormState("idle");
        setDownloadUrl(null);
        setFileName("");
        setTicker("");
        setBankCodes("");
    };

    // Show loading while checking auth
    if (isAuthenticated === null) {
        return (
            <>
                <div className="gradient-bg" />
                <div className="min-h-screen flex items-center justify-center">
                    <div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }} />
                </div>
            </>
        );
    }

    return (
        <>
            <div className="gradient-bg" />
            <div className="min-h-screen flex items-center justify-center p-6">
                <div className="w-full max-w-md">
                    {/* Header */}
                    <div className="text-center mb-8 fade-in">
                        <div
                            className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
                            style={{
                                background: "linear-gradient(135deg, #77be43 0%, #acd037 100%)",
                            }}
                        >
                            <svg
                                className="w-8 h-8 text-white"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                            >
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                                />
                            </svg>
                        </div>
                        <h1 className="text-3xl font-bold gradient-text mb-2">
                            Financial Reporting Tool
                        </h1>
                        <p className="text-gray-400">
                            Generate comprehensive financial statements in Excel format
                        </p>
                    </div>

                    {/* Tabs */}
                    <div className="flex bg-white/5 p-1 rounded-xl mb-6 fade-in" style={{ animationDelay: "0.05s" }}>
                        <button
                            onClick={() => { setActiveTab("sec"); handleReset(); }}
                            className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${activeTab === "sec"
                                ? "bg-[#acd037] text-black shadow-lg"
                                : "text-gray-400 hover:text-white"
                                }`}
                        >
                            SEC Scraper
                        </button>
                        <button
                            onClick={() => { setActiveTab("fdic"); handleReset(); }}
                            className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${activeTab === "fdic"
                                ? "bg-[#acd037] text-black shadow-lg"
                                : "text-gray-400 hover:text-white"
                                }`}
                        >
                            FDIC Scraper
                        </button>
                    </div>

                    {/* Card */}
                    <div
                        className="glass-card p-8 fade-in"
                        style={{ animationDelay: "0.1s" }}
                    >
                        {activeTab === "sec" ? (
                            <form onSubmit={handleSubmit}>
                                <div className="space-y-5">
                                    {/* Name Input */}
                                    <div>
                                        <label htmlFor="name" className="form-label">
                                            Your Name
                                        </label>
                                        <input
                                            type="text"
                                            id="name"
                                            className="form-input"
                                            placeholder="John Doe"
                                            value={name}
                                            onChange={(e) => setName(e.target.value)}
                                            required
                                            disabled={formState === "loading"}
                                        />
                                    </div>

                                    {/* Email Input */}
                                    <div>
                                        <label htmlFor="email" className="form-label">
                                            Email Address
                                        </label>
                                        <input
                                            type="email"
                                            id="email"
                                            className="form-input"
                                            placeholder="john@example.com"
                                            value={email}
                                            onChange={(e) => setEmail(e.target.value)}
                                            required
                                            disabled={formState === "loading"}
                                        />
                                    </div>

                                    {/* SEC Disclaimer */}
                                    <div className="text-xs text-gray-500 bg-white/5 rounded-lg p-3 border border-white/10">
                                        <p>
                                            <span className="font-medium text-gray-400">
                                                Privacy Notice:
                                            </span>{" "}
                                            To comply with SEC Regulation S-T, users must provide name
                                            and email. This data is not stored by the scraper.
                                        </p>
                                    </div>

                                    {/* Ticker Input */}
                                    <div>
                                        <label htmlFor="ticker" className="form-label">
                                            Company Ticker
                                        </label>
                                        <input
                                            type="text"
                                            id="ticker"
                                            className="form-input"
                                            placeholder="AAPL, MSFT, AMZN..."
                                            value={ticker}
                                            onChange={(e) => setTicker(e.target.value.toUpperCase())}
                                            required
                                            disabled={formState === "loading"}
                                            maxLength={10}
                                            style={{ textTransform: "uppercase" }}
                                        />
                                    </div>

                                    {/* Loading State */}
                                    {formState === "loading" && (
                                        <div className="fade-in">
                                            <div className="text-center py-4">
                                                <p className="text-gray-400 text-sm mb-3">
                                                    {statusMessage || "Processing..."}
                                                </p>
                                                <div className="progress-bar">
                                                    <div className="progress-bar-inner" />
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {/* Error State */}
                                    {formState === "error" && (
                                        <div className="error-message fade-in">
                                            <svg
                                                className="w-5 h-5 flex-shrink-0 mt-0.5"
                                                fill="currentColor"
                                                viewBox="0 0 20 20"
                                            >
                                                <path
                                                    fillRule="evenodd"
                                                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                                                    clipRule="evenodd"
                                                />
                                            </svg>
                                            <span>{errorMessage}</span>
                                        </div>
                                    )}

                                    {/* Success State */}
                                    {formState === "success" && (
                                        <div className="fade-in space-y-4">
                                            <div className="success-message">
                                                <svg
                                                    className="w-5 h-5 flex-shrink-0"
                                                    fill="currentColor"
                                                    viewBox="0 0 20 20"
                                                >
                                                    <path
                                                        fillRule="evenodd"
                                                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                                                        clipRule="evenodd"
                                                    />
                                                </svg>
                                                <span>Report generated successfully!</span>
                                            </div>
                                            <button
                                                type="button"
                                                className="btn-download"
                                                onClick={handleDownload}
                                            >
                                                <svg
                                                    className="w-5 h-5"
                                                    fill="none"
                                                    stroke="currentColor"
                                                    viewBox="0 0 24 24"
                                                >
                                                    <path
                                                        strokeLinecap="round"
                                                        strokeLinejoin="round"
                                                        strokeWidth={2}
                                                        d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                                                    />
                                                </svg>
                                                Download {fileName}
                                            </button>
                                            <button
                                                type="button"
                                                className="w-full py-3 text-sm text-gray-400 hover:text-white transition-colors"
                                                onClick={handleReset}
                                            >
                                                Generate another report
                                            </button>
                                        </div>
                                    )}

                                    {/* Submit Button */}
                                    {formState !== "success" && (
                                        <button
                                            type="submit"
                                            className="btn-primary"
                                            disabled={formState === "loading" || !name || !email || !ticker}
                                        >
                                            {formState === "loading" ? "Processing..." : "Generate Excel Report"}
                                        </button>
                                    )}
                                </div>
                            </form>
                        ) : (
                            <form onSubmit={handleFdicSubmit}>
                                <div className="space-y-5">
                                    <div className="text-xs text-gray-500 bg-white/5 rounded-lg p-3 border border-white/10 mb-4">
                                        <p>
                                            Enter FDIC Certificate numbers separated by commas.
                                        </p>
                                    </div>

                                    {/* Bank Codes Input */}
                                    <div>
                                        <label htmlFor="bankCodes" className="form-label">
                                            Bank Codes (CERTs)
                                        </label>
                                        <textarea
                                            id="bankCodes"
                                            className="form-input min-h-[100px]"
                                            placeholder="1105, 3832, 3973..."
                                            value={bankCodes}
                                            onChange={(e) => setBankCodes(e.target.value)}
                                            required
                                            disabled={formState === "loading"}
                                        />
                                    </div>

                                    {/* Loading State */}
                                    {formState === "loading" && (
                                        <div className="fade-in">
                                            <div className="text-center py-4">
                                                <p className="text-gray-400 text-sm mb-3">
                                                    {statusMessage || "Processing..."}
                                                </p>
                                                <div className="progress-bar">
                                                    <div className="progress-bar-inner" />
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {/* Error State */}
                                    {formState === "error" && (
                                        <div className="error-message fade-in">
                                            <svg
                                                className="w-5 h-5 flex-shrink-0 mt-0.5"
                                                fill="currentColor"
                                                viewBox="0 0 20 20"
                                            >
                                                <path
                                                    fillRule="evenodd"
                                                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                                                    clipRule="evenodd"
                                                />
                                            </svg>
                                            <span>{errorMessage}</span>
                                        </div>
                                    )}

                                    {/* Success State */}
                                    {formState === "success" && (
                                        <div className="fade-in space-y-4">
                                            <div className="success-message">
                                                <svg
                                                    className="w-5 h-5 flex-shrink-0"
                                                    fill="currentColor"
                                                    viewBox="0 0 20 20"
                                                >
                                                    <path
                                                        fillRule="evenodd"
                                                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                                                        clipRule="evenodd"
                                                    />
                                                </svg>
                                                <span>Report generated successfully!</span>
                                            </div>
                                            <button
                                                type="button"
                                                className="btn-download"
                                                onClick={handleDownload}
                                            >
                                                <svg
                                                    className="w-5 h-5"
                                                    fill="none"
                                                    stroke="currentColor"
                                                    viewBox="0 0 24 24"
                                                >
                                                    <path
                                                        strokeLinecap="round"
                                                        strokeLinejoin="round"
                                                        strokeWidth={2}
                                                        d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                                                    />
                                                </svg>
                                                Download {fileName}
                                            </button>
                                            <button
                                                type="button"
                                                className="w-full py-3 text-sm text-gray-400 hover:text-white transition-colors"
                                                onClick={handleReset}
                                            >
                                                Generate another report
                                            </button>
                                        </div>
                                    )}

                                    {/* Submit Button */}
                                    {formState !== "success" && (
                                        <button
                                            type="submit"
                                            className="btn-primary"
                                            disabled={formState === "loading" || !bankCodes}
                                        >
                                            {formState === "loading" ? "Processing..." : "Generate FDIC Report"}
                                        </button>
                                    )}
                                </div>
                            </form>
                        )}
                    </div>

                    {/* Footer with Logout */}
                    <div className="text-center mt-6 fade-in" style={{ animationDelay: "0.2s" }}>
                        <p className="text-gray-500 text-sm mb-2">
                            Data sourced from SEC EDGAR & FDIC databases
                        </p>
                        <button
                            onClick={handleLogout}
                            className="text-gray-600 text-xs hover:text-gray-400 transition-colors"
                        >
                            Sign out
                        </button>
                    </div>
                </div>
            </div>
        </>
    );
}
