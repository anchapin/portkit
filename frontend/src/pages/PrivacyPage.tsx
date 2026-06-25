/**
 * Privacy Policy Page
 */

import React from 'react';
import styles from './DocumentationSimple.module.css';

export const PrivacyPage: React.FC = () => {
  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1 className={styles.title}>Privacy Policy</h1>
        <p className={styles.subtitle}>
          Last updated:{' '}
          {new Date().toLocaleDateString('en-US', {
            month: 'long',
            day: 'numeric',
            year: 'numeric',
          })}
        </p>
      </header>

      <nav className={styles.navigation}>
        <a href="#data-collected" className={styles.navLink}>
          Data We Collect
        </a>
        <a href="#data-use" className={styles.navLink}>
          How We Use Data
        </a>
        <a href="#data-retention" className={styles.navLink}>
          Data Retention
        </a>
        <a href="#third-party" className={styles.navLink}>
          Third-Party Services
        </a>
        <a href="#user-rights" className={styles.navLink}>
          Your Rights
        </a>
        <a href="#gdpr" className={styles.navLink}>
          GDPR/CCPA
        </a>
        <a href="#cookies" className={styles.navLink}>
          Cookies
        </a>
        <a href="#contact" className={styles.navLink}>
          Contact
        </a>
      </nav>

      <section id="data-collected" className={styles.section}>
        <h2 className={styles.sectionTitle}>1. Data We Collect</h2>
        <h3 className={styles.sectionTitle}>Account Information</h3>
        <p>When you create an account, we collect:</p>
        <ul>
          <li>Email address</li>
          <li>Password (hashed and stored securely)</li>
          <li>Account preferences and settings</li>
          <li>Billing information (for paid tiers)</li>
        </ul>
        <h3 className={styles.sectionTitle}>Usage Data</h3>
        <p>We collect information about how you use our Service:</p>
        <ul>
          <li>Conversion history and analytics</li>
          <li>Features accessed and interactions</li>
          <li>Device information and browser type</li>
          <li>IP address and general location</li>
          <li>Error logs and performance data</li>
        </ul>
        <h3 className={styles.sectionTitle}>Uploaded Files</h3>
        <p>
          When you use our conversion service, you upload Minecraft mod files
          (&quot;User Content&quot;). These files are processed to provide the
          conversion service and may be temporarily stored for processing
          purposes.
        </p>
      </section>

      <section id="data-use" className={styles.section}>
        <h2 className={styles.sectionTitle}>2. How We Use Your Data</h2>
        <p>We use collected data to:</p>
        <ul>
          <li>Provide, maintain, and improve the Service</li>
          <li>Process your mod conversions and deliver results</li>
          <li>Create your account and manage your subscription</li>
          <li>Send service-related notifications and updates</li>
          <li>Respond to your support requests</li>
          <li>Analyze usage patterns to improve user experience</li>
          <li>Detect and prevent fraud or abuse</li>
          <li>Comply with legal obligations</li>
        </ul>
      </section>

      <section id="data-retention" className={styles.section}>
        <h2 className={styles.sectionTitle}>3. Data Retention</h2>
        <h3 className={styles.sectionTitle}>Uploaded Files</h3>
        <p>
          Uploaded mod files are retained for processing purposes and are
          typically deleted within 30 days of conversion completion. Files may
          be retained longer in encrypted backups for disaster recovery
          purposes.
        </p>
        <h3 className={styles.sectionTitle}>Account Data</h3>
        <p>
          Your account information is retained for as long as your account is
          active. Upon account deletion, your data is deleted within 30 days,
          except where retention is required by law.
        </p>
        <h3 className={styles.sectionTitle}>Analytics Data</h3>
        <p>
          Aggregated, anonymized analytics data may be retained indefinitely for
          service improvement purposes.
        </p>
      </section>

      <section id="third-party" className={styles.section}>
        <h2 className={styles.sectionTitle}>4. Third-Party Services</h2>
        <p>We use third-party services to operate and improve the Service:</p>
        <h3 className={styles.sectionTitle}>Payment Processing</h3>
        <p>
          <strong>Stripe</strong> - We use Stripe for payment processing. Stripe
          handles payment information directly and we do not store your full
          credit card details. Stripe&apos;s privacy policy applies to their
          data handling practices.
        </p>
        <h3 className={styles.sectionTitle}>Analytics</h3>
        <p>
          <strong>Plausible/PostHog</strong> - We use privacy-focused analytics
          to understand how users interact with our Service. These tools collect
          anonymized, aggregated data and do not use cookies or track personal
          information.
        </p>
        <h3 className={styles.sectionTitle}>AI Providers</h3>
        <p>
          <strong>OpenAI / Claude</strong> - Mod files are processed using AI
          services to perform conversions. These providers process data under
          their respective privacy policies and terms of service.
        </p>
        <h3 className={styles.sectionTitle}>Cloud Infrastructure</h3>
        <p>
          <strong>Fly.io / AWS</strong> - Our service is hosted on cloud
          infrastructure providers that process data under their privacy
          policies and terms.
        </p>
        <h3 className={styles.sectionTitle}>Authentication (OAuth Sign-In)</h3>
        <p>
          <strong>OAuth Providers (Discord, GitHub, Google).</strong> If you
          choose to sign in with one of these providers instead of creating a
          password, we receive a limited set of profile data to authenticate
          you and create your account. We request only the minimum scopes
          needed for sign-in:
        </p>
        <ul>
          <li>
            <strong>Discord</strong> ({' '}
            <code>identify</code>, <code>email</code> scopes) — we receive your
            Discord account ID, username, and email address.
          </li>
          <li>
            <strong>GitHub</strong> ({' '}
            <code>read:user</code>, <code>user:email</code> scopes) — we receive
            your GitHub account ID, username (login), and primary verified
            email address.
          </li>
          <li>
            <strong>Google</strong> ({' '}
            <code>openid</code>, <code>email</code>, <code>profile</code>{' '}
            scopes) — we receive your Google account ID, name, and email
            address.
          </li>
        </ul>
        <p>
          For each linked provider we store the provider name, your unique
          account ID at that provider, the email and username returned by the
          provider, and an encrypted access token used only to keep your
          session signed in. <strong>We never receive your provider
          password.</strong>
        </p>
        <p>
          We do <strong>not</strong> request access to your messages or DMs,
          your contacts or friends lists, your repositories or source code,
          your Gmail, Drive, or calendar, and we{' '}
          <strong>never post or take actions on your behalf</strong> on any
          provider. This data is used for authentication and account creation
          only — it is not used for marketing and is not sold. OAuth profile
          data is retained for the life of your account and deleted when your
          account is deleted; see the Data Retention section below and our{' '}
          <a href="/data-retention">Data Retention Policy</a> for details,
          including how to request deletion.
        </p>
      </section>

      <section id="user-rights" className={styles.section}>
        <h2 className={styles.sectionTitle}>5. Your Rights</h2>
        <p>You have the following rights regarding your personal data:</p>
        <h3 className={styles.sectionTitle}>Access</h3>
        <p>
          You can request a copy of your personal data by contacting us at
          privacy@portkit.cloud. We will provide your data in a portable format
          within 30 days.
        </p>
        <h3 className={styles.sectionTitle}>Correction</h3>
        <p>
          You can update your account information at any time through your
          account settings or by contacting support.
        </p>
        <h3 className={styles.sectionTitle}>Deletion</h3>
        <p>
          You can delete your account and request deletion of your personal data
          by contacting us at privacy@portkit.cloud. We will process deletion
          requests within 30 days.
        </p>
        <h3 className={styles.sectionTitle}>Data Export</h3>
        <p>
          You can export your conversion history and account data at any time
          through your account settings or by contacting support.
        </p>
        <h3 className={styles.sectionTitle}>Objection</h3>
        <p>
          You can object to certain processing of your data, such as marketing
          communications, by updating your preferences or contacting us.
        </p>
      </section>

      <section id="gdpr" className={styles.section}>
        <h2 className={styles.sectionTitle}>6. GDPR and CCPA Compliance</h2>
        <h3 className={styles.sectionTitle}>GDPR (EU Users)</h3>
        <p>
          If you are located in the European Economic Area (EEA), you have
          additional rights under the General Data Protection Regulation:
        </p>
        <ul>
          <li>Right to be informed about data collection and processing</li>
          <li>Right of access to your personal data</li>
          <li>Right to rectification of inaccurate data</li>
          <li>Right to erasure (&quot;right to be forgotten&quot;)</li>
          <li>Right to restrict processing</li>
          <li>Right to data portability</li>
          <li>Right to object to processing</li>
          <li>Rights related to automated decision making</li>
        </ul>
        <p>
          Our legal basis for processing personal data includes your consent,
          contract performance, and our legitimate interests in providing the
          Service.
        </p>
        <h3 className={styles.sectionTitle}>CCPA (California Users)</h3>
        <p>
          California residents have the right to know what personal information
          is collected, request deletion, and opt-out of the sale of personal
          information. We do not sell your personal information. Contact us to
          exercise your CCPA rights.
        </p>
        <p>
          For GDPR/CCPA requests, contact our Data Protection Officer at
          privacy@portkit.cloud.
        </p>
      </section>

      <section id="cookies" className={styles.section}>
        <h2 className={styles.sectionTitle}>7. Cookies</h2>
        <p>
          We use cookies and similar technologies to operate our Service. For
          detailed information about our cookie usage, please see our{' '}
          <a href="/cookies">Cookie Policy</a>.
        </p>
        <p>
          Essential cookies required for the Service to function cannot be
          disabled. Analytics and marketing cookies require your consent, which
          you can manage through our cookie consent banner.
        </p>
      </section>

      <section id="contact" className={styles.section}>
        <h2 className={styles.sectionTitle}>8. Contact Us</h2>
        <p>
          If you have any questions about this Privacy Policy or our data
          practices, please contact us:
        </p>
        <p>
          <strong>Email:</strong> privacy@portkit.cloud
          <br />
          <strong>Data Protection Officer:</strong> dpo@portkit.cloud
          <br />
          <strong>Address:</strong> ModPorter AI, [Address]
        </p>
      </section>
    </div>
  );
};

export default PrivacyPage;
