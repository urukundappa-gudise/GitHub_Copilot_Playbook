[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,
    [Parameter(Mandatory = $true)]
    [string]$StateBucketName,
    [string]$OutputDirectory = (Join-Path $env:TEMP ("aimplify-e2e-" + [guid]::NewGuid().ToString('N')))
)

$ErrorActionPreference = 'Stop'

function Invoke-AwsJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = & aws @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI command failed: aws $($Arguments -join ' ')"
    }
    return ($output | ConvertFrom-Json)
}

function Test-CertificateCoversHost {
    param(
        [Parameter(Mandatory = $true)][string[]]$Names,
        [Parameter(Mandatory = $true)][string]$HostName
    )

    foreach ($name in $Names) {
        if ($name -ieq $HostName) {
            return $true
        }
        if ($name.StartsWith('*.')) {
            $suffix = $name.Substring(1)
            if ($HostName.EndsWith($suffix, [StringComparison]::OrdinalIgnoreCase) -and
                $HostName.Split('.').Count -eq $name.Split('.').Count) {
                return $true
            }
        }
    }
    return $false
}

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Non-secret E2E variable JSON was not found: $ConfigPath"
}
if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory already exists; choose a fresh path: $OutputDirectory"
}

$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$required = @(
    'aws_region', 'stack_id', 'owner', 'app_domain_name', 'api_domain_name',
    'cloudfront_certificate_arn', 'alb_certificate_arn',
    'allowed_client_cidrs', 'image_uri', 'ecr_repository_arn',
    'azure_ad_tenant_id', 'azure_ad_client_id', 'azure_ad_redirect_uri',
    'azure_ad_post_logout_redirect_uri', 'azure_ad_client_secret_arn',
    'expiry_alert_topic_arn'
)
$propertyNames = @($config.PSObject.Properties.Name)
$missing = @($required | Where-Object { $_ -notin $propertyNames })
if ($missing.Count -gt 0) {
    throw "E2E variable JSON is missing required non-secret values: $($missing -join ', ')"
}
$allowed = $required + @(
    'database_username', 'expires_after_hours', 'vpc_cidr', 'instance_type',
    'db_instance_class', 'registry_prefix', 'state_bucket_name', 'state_key', 'created_at'
)
$unexpected = @($propertyNames | Where-Object { $_ -notin $allowed })
if ($unexpected.Count -gt 0) {
    throw "Unknown E2E variable names are rejected; review the template: $($unexpected -join ', ')"
}
$secretValueProperties = @($propertyNames | Where-Object { $_ -match '(?i)^(client_secret|database_password|password|access_token|refresh_token|private_key)$' })
if ($secretValueProperties.Count -gt 0) {
    throw "Secret values are not accepted in the E2E variable JSON: $($secretValueProperties -join ', ')"
}
if ($config.stack_id -notmatch '^[a-z0-9][a-z0-9-]{2,23}$') {
    throw 'stack_id must be 3-24 lowercase letters, digits, or hyphens.'
}

$stateKey = "e2e-sso/stacks/$($config.stack_id)/terraform.tfstate"
$registryPrefix = if ($config.registry_prefix) { [string]$config.registry_prefix } else { 'e2e-sso/registry' }
if (-not $registryPrefix.StartsWith('e2e-sso/') -or $registryPrefix.Contains('..')) {
    throw 'registry_prefix must stay under e2e-sso/.'
}
$createdAt = [DateTimeOffset]::UtcNow
$createdAtText = $createdAt.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture)
$expiresAtText = $createdAt.AddHours(72).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture)
$config | Add-Member -NotePropertyName state_bucket_name -NotePropertyValue $StateBucketName -Force
$config | Add-Member -NotePropertyName state_key -NotePropertyValue $stateKey -Force
$config | Add-Member -NotePropertyName created_at -NotePropertyValue $createdAtText -Force
$config | Add-Member -NotePropertyName expires_after_hours -NotePropertyValue 72 -Force

$identity = Invoke-AwsJson -Arguments @('sts', 'get-caller-identity', '--output', 'json')
$bucketLocation = Invoke-AwsJson -Arguments @('s3api', 'get-bucket-location', '--bucket', $StateBucketName, '--output', 'json')
$bucketRegion = if ($bucketLocation.LocationConstraint) { [string]$bucketLocation.LocationConstraint } else { 'us-east-1' }
if ($bucketRegion -ne $config.aws_region) {
    throw "State bucket region '$bucketRegion' must match the E2E AWS region '$($config.aws_region)'."
}
$publicAccess = Invoke-AwsJson -Arguments @('s3api', 'get-public-access-block', '--bucket', $StateBucketName, '--output', 'json')
if (-not ($publicAccess.PublicAccessBlockConfiguration.BlockPublicAcls -and
    $publicAccess.PublicAccessBlockConfiguration.BlockPublicPolicy -and
    $publicAccess.PublicAccessBlockConfiguration.IgnorePublicAcls -and
    $publicAccess.PublicAccessBlockConfiguration.RestrictPublicBuckets)) {
    throw 'The state bucket must block all public access before it can store E2E state and manifests.'
}
$versioning = Invoke-AwsJson -Arguments @('s3api', 'get-bucket-versioning', '--bucket', $StateBucketName, '--output', 'json')
if ($versioning.Status -ne 'Enabled') {
    throw 'The state bucket must have versioning enabled.'
}
$encryption = Invoke-AwsJson -Arguments @('s3api', 'get-bucket-encryption', '--bucket', $StateBucketName, '--output', 'json')
if (-not $encryption.ServerSideEncryptionConfiguration.Rules) {
    throw 'The state bucket must have default server-side encryption enabled.'
}
if ($config.app_domain_name -ine 'adlc.infovision.com' -or
    $config.api_domain_name -ine 'ai.adlc.infovision.com') {
    throw 'Use the approved app/API hostnames and manage their DNS through the existing Infovision DNS provider.'
}
$cloudFrontCertificate = Invoke-AwsJson -Arguments @(
    'acm', 'describe-certificate', '--region', 'us-east-1',
    '--certificate-arn', $config.cloudfront_certificate_arn, '--output', 'json'
)
if ($cloudFrontCertificate.Certificate.Status -ne 'ISSUED' -or
    -not (Test-CertificateCoversHost -Names $cloudFrontCertificate.Certificate.SubjectAlternativeNames -HostName $config.app_domain_name)) {
    throw 'The us-east-1 CloudFront certificate must be ISSUED and cover app_domain_name.'
}
$albCertificate = Invoke-AwsJson -Arguments @(
    'acm', 'describe-certificate', '--region', $config.aws_region,
    '--certificate-arn', $config.alb_certificate_arn, '--output', 'json'
)
if ($albCertificate.Certificate.Status -ne 'ISSUED' -or
    -not (Test-CertificateCoversHost -Names $albCertificate.Certificate.SubjectAlternativeNames -HostName $config.api_domain_name)) {
    throw 'The workload-region ALB certificate must be ISSUED and cover api_domain_name.'
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$variablesPath = Join-Path $OutputDirectory 'terraform.tfvars.json'
$manifestPath = Join-Path $OutputDirectory 'manifest.json'
$manifest = [ordered]@{
    stack_id   = [string]$config.stack_id
    owner      = [string]$config.owner
    created_at = $createdAtText
    expires_at = $expiresAtText
    state_key  = $stateKey
    variables  = $config
}
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($variablesPath, ($config | ConvertTo-Json -Depth 20), $utf8NoBom)
[System.IO.File]::WriteAllText($manifestPath, ([PSCustomObject]$manifest | ConvertTo-Json -Depth 20), $utf8NoBom)

$registryKey = "$registryPrefix/$($config.stack_id).json"
& aws s3api put-object --bucket $StateBucketName --key $registryKey --body $manifestPath --content-type 'application/json' --output json | Out-Null
if ($LASTEXITCODE -ne 0) {
    Remove-Item -LiteralPath $OutputDirectory -Recurse -Force
    throw 'Could not register the expiry manifest; do not run Terraform apply.'
}

Write-Output "Stack registration created by AWS account $($identity.Account)."
Write-Output "State key: $stateKey"
Write-Output "Expiry: $expiresAtText UTC"
Write-Output "Terraform variables: $variablesPath"
Write-Output 'Review a Terraform plan before apply. This script does not apply or destroy infrastructure.'
