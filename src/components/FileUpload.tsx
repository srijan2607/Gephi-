'use client';

import React, { useCallback, useState } from 'react';

interface ProcessingResult {
  success: boolean;
  stats?: {
    rows: number;
    nodes: number;
    edges: number;
    categories: number;
    jobs: number;
    skills: number;
  };
  files?: {
    nodes: string;
    edges: string;
    graphml: string | null;
  };
  error?: string;
  largeDataset?: boolean;
}

export default function FileUpload() {
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [result, setResult] = useState<ProcessingResult | null>(null);

  const processFile = useCallback(async (file: File) => {
    setIsProcessing(true);
    setFileName(file.name);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/api/process', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setResult({
          success: true,
          stats: data.stats,
          files: data.files,
          largeDataset: data.largeDataset,
        });
      } else {
        setResult({
          success: false,
          error: data.error || 'Processing failed',
        });
      }
    } catch (err) {
      setResult({
        success: false,
        error: err instanceof Error ? err.message : 'Upload failed',
      });
    } finally {
      setIsProcessing(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    if (isProcessing) return;

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      processFile(files[0]);
    }
  }, [isProcessing, processFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!isProcessing) {
      setIsDragging(true);
    }
  }, [isProcessing]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      processFile(files[0]);
    }
  }, [processFile]);

  const handleReset = useCallback(() => {
    setFileName(null);
    setResult(null);
  }, []);

  return (
    <div className="space-y-6">
      {/* Upload Area */}
      <div
        className={`
          border-2 border-dashed rounded-lg p-8 text-center transition-colors
          ${isDragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300'}
          ${isProcessing ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-blue-400'}
        `}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => {
          if (!isProcessing) {
            document.getElementById('file-input')?.click();
          }
        }}
      >
        <input
          id="file-input"
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={handleFileInput}
          disabled={isProcessing}
        />

        {isProcessing ? (
          <div className="flex flex-col items-center gap-3">
            <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-500 border-t-transparent"></div>
            <p className="text-lg font-medium text-gray-700">Processing {fileName}...</p>
            <p className="text-sm text-gray-500">This may take a while for large files</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <svg
              className="w-16 h-16 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            <p className="text-xl font-medium text-gray-700">
              Drop your file here
            </p>
            <p className="text-gray-500">or click to browse</p>
            <p className="text-sm text-gray-400 mt-2">
              Supports CSV and Excel files (.xlsx, .xls)
            </p>
          </div>
        )}
      </div>

      {/* Results */}
      {result && (
        <div className={`rounded-lg p-6 ${result.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
          {result.success ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-green-800">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span className="text-lg font-semibold">Processing Complete!</span>
                </div>
                <button
                  onClick={handleReset}
                  className="text-sm text-green-700 hover:text-green-900 underline"
                >
                  Process another file
                </button>
              </div>

              {result.stats && (
                <>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="bg-white rounded-lg p-4 text-center shadow-sm">
                      <div className="text-3xl font-bold text-gray-800">{result.stats.rows.toLocaleString()}</div>
                      <div className="text-gray-500">Rows Processed</div>
                    </div>
                    <div className="bg-white rounded-lg p-4 text-center shadow-sm">
                      <div className="text-3xl font-bold text-gray-800">{result.stats.nodes.toLocaleString()}</div>
                      <div className="text-gray-500">Total Nodes</div>
                    </div>
                    <div className="bg-white rounded-lg p-4 text-center shadow-sm">
                      <div className="text-3xl font-bold text-gray-800">{result.stats.edges.toLocaleString()}</div>
                      <div className="text-gray-500">Total Edges</div>
                    </div>
                  </div>

                  <div className="bg-white rounded-lg p-4 shadow-sm">
                    <h4 className="font-medium text-gray-700 mb-2">Node Breakdown</h4>
                    <div className="flex gap-6 text-sm">
                      <div>
                        <span className="text-gray-500">Categories:</span>{' '}
                        <span className="font-semibold text-gray-800">{result.stats.categories.toLocaleString()}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Jobs:</span>{' '}
                        <span className="font-semibold text-gray-800">{result.stats.jobs.toLocaleString()}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Skills:</span>{' '}
                        <span className="font-semibold text-gray-800">{result.stats.skills.toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                </>
              )}

              {result.files && (
                <div className="space-y-3">
                  {result.largeDataset && (
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-sm text-yellow-800">
                      <p className="font-medium">Large Dataset Detected</p>
                      <p>GraphML not generated to save memory. Import the CSV files into Gephi using:</p>
                      <ol className="list-decimal ml-4 mt-1">
                        <li>File → Import Spreadsheet → Select nodes.csv (as Nodes table)</li>
                        <li>File → Import Spreadsheet → Select edges.csv (as Edges table)</li>
                      </ol>
                    </div>
                  )}
                  {result.files.graphml && (
                    <a
                      href={result.files.graphml}
                      download="graph.graphml"
                      className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      Download graph.graphml (Recommended for Gephi)
                    </a>
                  )}
                  <div className="flex gap-3">
                    <a
                      href={result.files.nodes}
                      download="nodes.csv"
                      className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg transition-colors text-sm font-medium ${result.largeDataset ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      nodes.csv
                    </a>
                    <a
                      href={result.files.edges}
                      download="edges.csv"
                      className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg transition-colors text-sm font-medium ${result.largeDataset ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      edges.csv
                    </a>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-3 text-red-800">
              <svg className="w-6 h-6 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="font-semibold">Error Processing File</p>
                <p className="text-sm">{result.error}</p>
              </div>
              <button
                onClick={handleReset}
                className="ml-auto text-sm text-red-700 hover:text-red-900 underline"
              >
                Try again
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
