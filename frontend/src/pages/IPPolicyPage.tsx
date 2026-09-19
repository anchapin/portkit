/**
 * IP Policy Page - DMCA / Copyright / Intellectual Property Policy
 */

import React from 'react';
import styles from './DocumentationSimple.module.css';

export const IPPolicyPage: React.FC = () => {
  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1 className={styles.title}>DMCA / Copyright / IP Policy</h1>
        <p className={styles.subtitle}>Last updated: May 3, 2026</p>
      </header>

      <nav className={styles.navigation}>
        <a href="#overview" className={styles.navLink}>
          Overview
        </a>
        <a href="#license-detection" className={styles.navLink}>
          License Detection
        </a>
        <a href="#user-warranties" className={styles.navLink}>
          User Warranties
        </a>
        <a href="#dmca" className={styles.navLink}>
          DMCA Process
        </a>
        <a href="#attribution" className={styles.navLink}>
          Attribution
        </a>
        <a href="#contact" className={styles.navLink}>
          Contact
        </a>
      </nav>

      <section id="overview" className={styles.section}>
        <h2 className={styles.sectionTitle}>1. Overview</h2>
        <p>
          PortKit converts Minecraft Java Edition mods to Bedrock Edition
          add-ons. Before using the Service, you must understand that:
        </p>
        <ul>
          <li>
            <strong>Minecraft mods are copyrighted software.</strong> Most
            popular mods use restrictive licenses that prohibit unauthorized
            conversion.
          </li>
          <li>
            <strong>
              Converting someone else&apos;s mod without permission may
              constitute copyright infringement.
            </strong>{' '}
            "No license" does not mean "free to use."
          </li>
          <li>
            <strong>You are responsible</strong> for ensuring you have the legal
            right to convert any mod you upload.
          </li>
        </ul>
      </section>

      <section id="license-detection" className={styles.section}>
        <h2 className={styles.sectionTitle}>2. Mod License Detection</h2>
        <p>
          Before conversion, PortKit automatically scans uploaded mods for
          license indicators:
        </p>
        <ul>
          <li>LICENSE, LICENSE.md, or LICENSE.txt files</li>
          <li>META-INF/MANIFEST.MF metadata</li>
          <li>pack.mcmeta for Minecraft pack information</li>
          <li>CurseForge/Modrinth API metadata (when available)</li>
        </ul>
        <p>
          Mods with <strong>All Rights Reserved (ARR)</strong> or other
          restrictive licenses are flagged with a warning. You must confirm you
          have authorization before proceeding with such conversions.
        </p>
        <p>
          <strong>Permissive licenses</strong> (MIT, Apache 2.0, BSD, CC0, GPL
          3.0+, Unlicense) are generally safe to convert.
        </p>
      </section>

      <section id="user-warranties" className={styles.section}>
        <h2 className={styles.sectionTitle}>
          3. User Conversion Authorization Warranty
        </h2>
        <p>By using PortKit, you represent and warrant that:</p>
        <ul>
          <li>
            You are the <strong>original mod author</strong>, OR
          </li>
          <li>
            You have <strong>explicit written permission</strong> from the mod
            author to convert their mod, OR
          </li>
          <li>
            The mod is licensed under a <strong>permissive license</strong> that
            permits derivative works
          </li>
        </ul>
        <p>
          You agree to indemnify and hold harmless PortKit from any claims
          arising from unauthorized conversion of any mod you upload.
        </p>
      </section>

      <section id="dmca" className={styles.section}>
        <h2 className={styles.sectionTitle}>4. DMCA Takedown Procedure</h2>
        <p>
          PortKit complies with the Digital Millennium Copyright Act (DMCA). If
          you believe your copyrighted work has been infringed:
        </p>
        <h3 className={styles.sectionTitle}>Submit a Takedown Notice</h3>
        <p>
          Email: <strong>dmca@portkit.ai</strong>
        </p>
        <p>
          Valid notices must include: (1) identification of copyrighted work,
          (2) identification of infringing material, (3) good faith belief
          statement, (4) accuracy attestation under penalty of perjury, (5)
          contact information, and (6) signature.
        </p>
        <h3 className={styles.sectionTitle}>Our Response</h3>
        <ul>
          <li>Acknowledge receipt within 4 hours</li>
          <li>Remove or disable infringing content within 24 hours</li>
          <li>Notify the affected user within 48 hours</li>
        </ul>
        <h3 className={styles.sectionTitle}>Counter-Notice</h3>
        <p>
          Users who believe their content was wrongly removed may submit a
          counter-notice. Upon receipt, we have 10-14 days to reinstate the
          content before it remains removed.
        </p>
      </section>

      <section id="attribution" className={styles.section}>
        <h2 className={styles.sectionTitle}>
          5. Attribution in Converted Output
        </h2>
        <p>
          All converted .mcaddon files include original mod attribution in the
          manifest:
        </p>
        <p>
          <em>
            &quot;Converted from [Mod Name] by [Author]. Original license:
            [License]. Converted by PortKit.&quot;
          </em>
        </p>
        <p>
          If the original license cannot be determined, the manifest includes a
          note directing copyright holders to contact us.
        </p>
      </section>

      <section id="related-docs" className={styles.section}>
        <h2 className={styles.sectionTitle}>6. Related Documents</h2>
        <ul>
          <li>
            <a href="/terms">Terms of Service</a>
          </li>
          <li>
            <a href="/privacy">Privacy Policy</a>
          </li>
          <li>
            <a href="/cookies">Cookie Policy</a>
          </li>
        </ul>
      </section>

      <section id="contact" className={styles.section}>
        <h2 className={styles.sectionTitle}>7. Contact</h2>
        <p>For IP-related inquiries:</p>
        <p>
          <strong>General IP questions:</strong> ip@portkit.ai
          <br />
          <strong>DMCA notices:</strong> dmca@portkit.ai
          <br />
          <strong>Legal matters:</strong> legal@portkit.ai
        </p>
      </section>
    </div>
  );
};

export default IPPolicyPage;
