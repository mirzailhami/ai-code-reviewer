document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('uploadForm');
  const resultsContainer = document.getElementById('resultsContainer');
  const emptyState = document.getElementById('emptyState');
  const screeningResults = document.getElementById('screeningResults');
  const securityFindings = document.getElementById('securityFindings');
  const qualityMetrics = document.getElementById('qualityMetrics');
  const performanceMetrics = document.getElementById('performanceMetrics');
  const scorecard = document.getElementById('scorecard');
  const nlpResults = document.getElementById('nlpResults');
  const analyzeBtn = document.getElementById('analyzeBtn');
  const btnText = document.getElementById('btnText');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    // Disable button and show loading state
    analyzeBtn.disabled = true;
    btnText.textContent = 'Let we work, please wait...';

    const formData = new FormData(form);
    console.log('FormData:', Object.fromEntries(formData));
    resultsContainer.classList.add('hidden');
    emptyState.classList.remove('hidden');

    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();

      // Check for error response
      if (data.error) {
        resultsContainer.innerHTML = `
          <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
            <strong>Error:</strong> ${data.error}
          </div>
          <div class="bg-white p-6 rounded-lg shadow mt-6">
            <h3 class="text-lg font-semibold mb-2 text-gray-700">Screening Results</h3>
            <p><strong>Valid:</strong> ${data.screening_result?.valid ? 'Yes' : 'No'}</p>
            ${
              data.screening_result?.reason
                ? `<p><strong>Reason:</strong> ${data.screening_result.reason}</p>`
                : ''
            }
            <p><strong>Languages Detected:</strong> ${
              data.screening_result?.languages?.length
                ? data.screening_result.languages.join(', ')
                : 'None'
            }</p>
          </div>
        `;
        resultsContainer.classList.remove('hidden');
        emptyState.classList.add('hidden');
        return;
      }

      emptyState.classList.add('hidden');
      resultsContainer.classList.remove('hidden');

      // Screening Results
      screeningResults.innerHTML = `
        <h3 class="text-lg font-semibold mb-2 text-gray-700">Screening Results</h3>
        <p><strong>Valid:</strong> ${data.screening_result?.valid ? 'Yes' : 'No'}</p>
        ${
          data.screening_result?.reason
            ? `<p><strong>Reason:</strong> ${data.screening_result.reason}</p>`
            : ''
        }
        <p><strong>Languages Detected:</strong> ${
          data.screening_result?.languages?.length
            ? data.screening_result.languages.join(', ')
            : 'None'
        }</p>
      `;

      // Scorecard (NLP Results)
      nlpResults.innerHTML = `
        <h3 class="text-lg font-semibold mb-2 text-gray-700">Scorecard</h3>
        ${
          data.scorecard?.length
            ? data.scorecard
                .map(
                  (r) => `
                  <div class="border-l-4 border-blue-500 pl-4 mb-2">
                    <p><strong>Question:</strong> ${r.question || 'N/A'}</p>
                    <p><strong>Category:</strong> ${r.category || 'N/A'}</p>
                    <p><strong>Answer:</strong> ${r.answer || 'No answer provided'}</p>
                    <p><strong>Confidence:</strong> ${r.confidence || 0}/5</p>
                    <p><strong>Weight:</strong> ${r.weight || 0}</p>
                  </div>`
                )
                .join('')
            : '<p class="text-gray-500">No scorecard results available.</p>'
        }
      `;

      // Security Findings
      securityFindings.innerHTML = `
        <h3 class="text-lg font-semibold mb-2 text-gray-700">Security Findings</h3>
        ${
          data.security_findings?.length
            ? data.security_findings
                .map(
                  (f) => `
                  <div class="border-l-4 border-red-500 pl-4 mb-2">
                    <p><strong>Issue:</strong> ${f.issue || 'N/A'}</p>
                    <p><strong>Type:</strong> ${f.type || 'N/A'}</p>
                    <p><strong>Severity:</strong> ${f.severity || 'N/A'}</p>
                    <p><strong>Confidence:</strong> ${f.confidence || 0}/5</p>
                    <p><strong>File:</strong> ${f.file || 'N/A'}</p>
                    <p><strong>Recommendation:</strong> ${f.recommendation || 'N/A'}</p>
                  </div>`
                )
                .join('')
            : '<p class="text-gray-500">No security issues found.</p>'
        }
      `;

      // Quality Metrics
      qualityMetrics.innerHTML = `
        <h3 class="text-lg font-semibold mb-2 text-gray-700">Quality Metrics</h3>
        <p><strong>Maintainability Score:</strong> ${data.quality_metrics?.maintainability_score || 0}/100</p>
        <p><strong>Code Smells:</strong> ${data.quality_metrics?.code_smells || 0}</p>
        <p><strong>Documentation Coverage:</strong> ${data.quality_metrics?.doc_coverage || 0}/100</p>
      `;

      // Performance Metrics
      performanceMetrics.innerHTML = `
        <h3 class="text-lg font-semibold mb-2 text-gray-700">Performance Metrics</h3>
        <p><strong>Rating:</strong> ${data.performance_metrics?.rating || 0}/100</p>
        <p><strong>Bottlenecks:</strong> ${data.performance_metrics?.bottlenecks?.length ? data.performance_metrics.bottlenecks.join(', ') : 'None'}</p>
        <p><strong>Optimization Suggestions:</strong> ${data.performance_metrics?.optimization_suggestions?.length ? data.performance_metrics.optimization_suggestions.join(', ') : 'None'}</p>
      `;

      // Score Summary
      const scorecardScore = data.scorecard?.length
        ? data.scorecard.reduce((sum, r) => sum + (r.confidence * r.weight), 0) /
          data.scorecard.reduce((sum, r) => sum + r.weight, 0) * 20 // Normalize to 0-100
        : 0;
      scorecard.innerHTML = `
        <h3 class="text-lg font-semibold mb-2 text-gray-700">Score Summary</h3>
        <div class="mb-3">
          <div class="flex justify-between text-sm mb-1">
            <span>Code Quality</span>
            <span>${data.summary?.code_quality || 0}/100</span>
          </div>
          <div class="w-full bg-gray-200 rounded-full h-2">
            <div class="bg-blue-600 h-2 rounded-full" style="width: ${data.summary?.code_quality || 0}%"></div>
          </div>
        </div>
        <div class="mb-3">
          <div class="flex justify-between text-sm mb-1">
            <span>Security</span>
            <span>${data.summary?.security || 0}/100</span>
          </div>
          <div class="w-full bg-gray-200 rounded-full h-2">
            <div class="bg-blue-600 h-2 rounded-full" style="width: ${data.summary?.security || 0}%"></div>
          </div>
        </div>
        <div class="mb-3">
          <div class="flex justify-between text-sm mb-1">
            <span>Performance</span>
            <span>${data.summary?.performance || 0}/100</span>
          </div>
          <div class="w-full bg-gray-200 rounded-full h-2">
            <div class="bg-blue-600 h-2 rounded-full" style="width: ${data.summary?.performance || 0}%"></div>
          </div>
        </div>
        <div class="mb-3">
          <div class="flex justify-between text-sm mb-1">
            <span>Scorecard</span>
            <span>${Math.round(scorecardScore)}/100</span>
          </div>
          <div class="w-full bg-gray-200 rounded-full h-2">
            <div class="bg-blue-600 h-2 rounded-full" style="width: ${scorecardScore}%"></div>
          </div>
        </div>
        <div class="mb-3">
          <div class="flex justify-between text-sm mb-1">
            <span>Total</span>
            <span>${parseFloat(data.summary?.total || 0).toFixed(1)}/100</span>
          </div>
          <div class="w-full bg-gray-200 rounded-full h-2">
            <div class="bg-blue-600 h-2 rounded-full" style="width: ${data.summary?.total || 0}%"></div>
          </div>
        </div>
      `;
    } catch (error) {
      console.error('Error:', error);
      resultsContainer.innerHTML = `
        <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          <strong>Error:</strong> ${error.message}
        </div>
      `;
      resultsContainer.classList.remove('hidden');
      emptyState.classList.add('hidden');
    } finally {
      // Re-enable button and restore text
      analyzeBtn.disabled = false;
      btnText.textContent = 'Analyze Code';
    }
  });
});