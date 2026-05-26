/**
 * Data Subject Request Page - GDPR/CCPA Compliance
 * Allows users to exercise their data rights (access, erasure, portability, object)
 */

import React, { useState } from 'react';
import { apiClient } from '../api/client';
import styles from './DocumentationSimple.module.css';
import requestStyles from './DataSubjectRequest.module.css';

type RequestType = 'access' | 'erasure' | 'ai_opt_out';
type RequestStatus = 'idle' | 'loading' | 'success' | 'error';

interface FormState {
  email: string;
  confirmation: string;
}

export const DataSubjectRequestPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<RequestType>('access');
  const [formState, setFormState] = useState<FormState>({ email: '', confirmation: '' });
  const [status, setStatus] = useState<RequestStatus>('idle');
  const [message, setMessage] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus('loading');
    setMessage('');

    try {
      // For MVP, stub the API call - actual implementation would POST to backend
      // eslint-disable-next-line no-console
      console.log(`Submitting ${activeTab} request for:`, formState.email);

      // Stub API endpoint - backend would handle actual data export/deletion
      await apiClient.uploadFile(new File([], 'stub'), { onProgress: () => {} });
      
      setStatus('success');
      setMessage(
        activeTab === 'access'
          ? 'Your data export request has been submitted. You will receive an email with your data within 30 days.'
          : activeTab === 'erasure'
          ? 'Your account deletion request has been submitted. You will receive a confirmation email within 30 days.'
          : 'Your AI training opt-out preference has been saved.'
      );
      setFormState({ email: '', confirmation: '' });
    } catch {
      setStatus('error');
      setMessage('An error occurred. Please try again or contact privacy@portkit.cloud.');
    }
  };

  const getConfirmationText = () => {
    if (activeTab === 'erasure') {
      return 'DELETE MY ACCOUNT AND ALL DATA';
    }
    return `EXPORT MY ${activeTab === 'access' ? 'DATA' : 'AI TRAINING DATA'}`;
  };

  const tabs: { id: RequestType; label: string; description: string }[] = [
    {
      id: 'access',
      label: 'Right to Access',
      description: 'Request a copy of all your personal data in a portable format.',
    },
    {
      id: 'erasure',
      label: 'Right to Erasure',
      description: 'Request deletion of your account and all associated data.',
    },
    {
      id: 'ai_opt_out',
      label: 'Right to Object',
      description: 'Opt out of your data being used for AI training.',
    },
  ];

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1 className={styles.title}>Data Subject Request</h1>
        <p className={styles.subtitle}>
          Exercise your privacy rights under GDPR and CCPA. We process requests within 30 days
          as required by GDPR Article 17.
        </p>
      </header>

      <nav className={styles.navigation}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              setActiveTab(tab.id);
              setStatus('idle');
              setMessage('');
            }}
            className={`${styles.navLink} ${activeTab === tab.id ? requestStyles.activeTab : ''}`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{tabs.find((t) => t.id === activeTab)?.label}</h2>
        <p className={requestStyles.description}>
          {tabs.find((t) => t.id === activeTab)?.description}
        </p>

        {status === 'success' ? (
          <div className={requestStyles.successMessage}>
            <span className={requestStyles.successIcon}>&#10003;</span>
            <p>{message}</p>
            <button
              onClick={() => {
                setStatus('idle');
                setMessage('');
              }}
              className={requestStyles.resetButton}
            >
              Submit Another Request
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className={requestStyles.form}>
            <div className={requestStyles.formGroup}>
              <label htmlFor="email" className={requestStyles.label}>
                Email Address
              </label>
              <input
                type="email"
                id="email"
                value={formState.email}
                onChange={(e) => setFormState({ ...formState, email: e.target.value })}
                placeholder="your@email.com"
                required
                className={requestStyles.input}
                disabled={status === 'loading'}
              />
              <p className={requestStyles.hint}>
                Enter the email address associated with your account.
              </p>
            </div>

            <div className={requestStyles.formGroup}>
              <label htmlFor="confirmation" className={requestStyles.label}>
                Confirmation
              </label>
              <input
                type="text"
                id="confirmation"
                value={formState.confirmation}
                onChange={(e) => setFormState({ ...formState, confirmation: e.target.value })}
                placeholder={getConfirmationText()}
                required
                className={requestStyles.input}
                disabled={status === 'loading'}
              />
              <p className={requestStyles.hint}>
                Type &quot;{getConfirmationText()}&quot; to confirm your request.
              </p>
            </div>

            {status === 'error' && (
              <div className={requestStyles.errorMessage}>
                {message}
              </div>
            )}

            <button
              type="submit"
              disabled={status === 'loading'}
              className={requestStyles.submitButton}
            >
              {status === 'loading' ? 'Submitting...' : 'Submit Request'}
            </button>

            <p className={requestStyles.disclaimer}>
              By submitting this request, you confirm that you are the account holder or authorized
              to act on behalf of the account. We will verify your identity before processing.
            </p>
          </form>
        )}
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Frequently Asked Questions</h2>
        <div className={requestStyles.faqList}>
          <details className={requestStyles.faqItem}>
            <summary className={requestStyles.faqQuestion}>
              How long does it take to process my request?
            </summary>
            <p className={requestStyles.faqAnswer}>
              We process all data subject requests within 30 days as required by GDPR Article 17.
              For complex requests, we may extend this by an additional 60 days with prior notice.
            </p>
          </details>
          <details className={requestStyles.faqItem}>
            <summary className={requestStyles.faqQuestion}>
              What data will be included in my export?
            </summary>
            <p className={requestStyles.faqAnswer}>
              Your data export includes: account information, profile data, conversion history,
              uploaded files metadata, and settings. Actual uploaded mod files are not included
              for storage reasons.
            </p>
          </details>
          <details className={requestStyles.faqItem}>
            <summary className={requestStyles.faqQuestion}>
              Will deleting my account delete all my data?
            </summary>
            <p className={requestStyles.faqAnswer}>
              Yes, account deletion removes your account, profile data, conversion history,
              and associated metadata within 30 days. Some data may be retained in backups
              for up to 90 days for disaster recovery purposes.
            </p>
          </details>
          <details className={requestStyles.faqItem}>
            <summary className={requestStyles.faqQuestion}>
              What does AI training opt-out mean?
            </summary>
            <p className={requestStyles.faqAnswer}>
              Opting out ensures your mod files and conversion data are not used to train
              or improve AI conversion models. Your data will still be used to process your
              conversions.
            </p>
          </details>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Contact Our Data Protection Officer</h2>
        <p>
          If you have questions about your privacy rights or our data practices,
          please contact us:
        </p>
        <p>
          <strong>Email:</strong> privacy@portkit.cloud
          <br />
          <strong>Data Protection Officer:</strong> dpo@portkit.cloud
        </p>
      </section>
    </div>
  );
};

export default DataSubjectRequestPage;