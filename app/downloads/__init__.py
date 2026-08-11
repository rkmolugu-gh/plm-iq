"""Resumable downloads for files served from tenant-private Gitea repos.

Implements HTTP byte-range (206 Partial Content) so interrupted downloads resume
in the browser or any Range-aware client. Generated ZIPs are cached to disk so
multi-file assemblies/folders become fixed-size and rangeable.

Design: docs/download-manager.md
"""
