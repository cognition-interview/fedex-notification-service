<?php

declare(strict_types=1);

require __DIR__ . '/../vendor/autoload.php';

// Provide dummy env vars so classes that read them in constructors don't blow up
$_ENV['POSTGRES_CONNECTION_STRING'] = 'postgresql://user:pass@localhost:5432/testdb';
$_ENV['AZURE_EMAIL_CONNECTION_STRING'] = 'endpoint=https://test.communication.azure.com;accesskey=' . base64_encode('test-key');
$_ENV['AZURE_EMAIL_FROM_ADDRESS'] = 'noreply@test.com';
