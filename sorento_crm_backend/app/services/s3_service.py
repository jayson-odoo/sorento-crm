"""S3 service for file storage operations."""
import os
import logging
from typing import Optional
from pathlib import Path
import boto3
from botocore.exceptions import ClientError, BotoCoreError
from botocore.config import Config

logger = logging.getLogger(__name__)

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    # Load .env file from the backend directory
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.debug(f"Loaded .env file from {env_path}")
    else:
        # Try loading from current directory
        load_dotenv()
        logger.debug("Loaded .env file from current directory")
except ImportError:
    # python-dotenv not installed, rely on environment variables being set
    logger.warning("python-dotenv not installed. Environment variables must be set manually.")


class S3Service:
    """Service for S3 file operations."""
    
    def __init__(self):
        """Initialize S3 client from environment variables."""
        self.access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
        
        missing = []
        if not (self.access_key_id and self.access_key_id.strip()):
            missing.append("AWS_ACCESS_KEY_ID")
        if not (self.secret_access_key and self.secret_access_key.strip()):
            missing.append("AWS_SECRET_ACCESS_KEY")
        if not (self.bucket_name and self.bucket_name.strip()):
            missing.append("AWS_S3_BUCKET_NAME")
        if missing:
            raise ValueError(
                "S3 configuration incomplete: set the following in the backend environment: "
                + ", ".join(missing)
            )
        
        # Configure boto3 with retry settings
        config = Config(
            retries={
                'max_attempts': 3,
                'mode': 'standard'
            }
        )
        
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name=self.region,
            config=config
        )
    
    def upload_file(
        self,
        file_content: bytes,
        file_path: str,
        content_type: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Upload file to S3.
        
        Args:
            file_content: File content as bytes
            file_path: S3 key (path) where file will be stored
            content_type: MIME type of the file (optional)
        
        Returns:
            Tuple of (S3 key, S3 URL) where file was stored
        
        Raises:
            Exception: If upload fails
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_path,
                Body=file_content,
                **extra_args
            )
            
            # Generate S3 URL
            s3_url = self.get_file_url(file_path)
            
            logger.info(f"Successfully uploaded file to S3: {file_path}")
            return file_path, s3_url
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"S3 upload error ({error_code}): {error_message}")
            raise Exception(f"Failed to upload file to S3: {error_message}")
        
        except BotoCoreError as e:
            logger.error(f"S3 connection error: {str(e)}")
            raise Exception(f"Failed to connect to S3: {str(e)}")
    
    def get_file_url(self, file_path: str) -> str:
        """
        Get the S3 URL for a file.
        
        Args:
            file_path: S3 key (path) of the file
        
        Returns:
            S3 URL (https://...)
        """
        # Construct S3 URL
        # Format: https://{bucket}.s3.{region}.amazonaws.com/{key}
        # Or: https://s3.{region}.amazonaws.com/{bucket}/{key}
        if self.region == "us-east-1":
            # us-east-1 uses a different URL format
            url = f"https://{self.bucket_name}.s3.amazonaws.com/{file_path}"
        else:
            url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{file_path}"
        
        return url
    
    def download_file(self, file_path: str) -> bytes:
        """
        Download file from S3.
        
        Args:
            file_path: S3 key (path) of the file to download
        
        Returns:
            File content as bytes
        
        Raises:
            Exception: If download fails or file not found
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            
            file_content = response['Body'].read()
            logger.info(f"Successfully downloaded file from S3: {file_path}")
            return file_content
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            
            if error_code == 'NoSuchKey':
                logger.error(f"File not found in S3: {file_path}")
                raise Exception(f"File not found: {file_path}")
            
            logger.error(f"S3 download error ({error_code}): {error_message}")
            raise Exception(f"Failed to download file from S3: {error_message}")
        
        except BotoCoreError as e:
            logger.error(f"S3 connection error: {str(e)}")
            raise Exception(f"Failed to connect to S3: {str(e)}")
    
    def delete_file(self, file_path: str) -> bool:
        """
        Delete file from S3.
        
        Args:
            file_path: S3 key (path) of the file to delete
        
        Returns:
            True if deletion was successful
        
        Raises:
            Exception: If deletion fails
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            
            logger.info(f"Successfully deleted file from S3: {file_path}")
            return True
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"S3 delete error ({error_code}): {error_message}")
            raise Exception(f"Failed to delete file from S3: {error_message}")
        
        except BotoCoreError as e:
            logger.error(f"S3 connection error: {str(e)}")
            raise Exception(f"Failed to connect to S3: {str(e)}")
    
    def get_presigned_url(
        self,
        file_path: str,
        expiration: int = 3600
    ) -> str:
        """
        Generate presigned URL for direct file access.
        
        Args:
            file_path: S3 key (path) of the file
            expiration: URL expiration time in seconds (default: 1 hour)
        
        Returns:
            Presigned URL string
        
        Raises:
            Exception: If URL generation fails
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': file_path
                },
                ExpiresIn=expiration
            )
            
            logger.info(f"Generated presigned URL for: {file_path}")
            return url
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"S3 presigned URL error ({error_code}): {error_message}")
            raise Exception(f"Failed to generate presigned URL: {error_message}")
        
        except BotoCoreError as e:
            logger.error(f"S3 connection error: {str(e)}")
            raise Exception(f"Failed to connect to S3: {str(e)}")
    
    def file_exists(self, file_path: str) -> bool:
        """
        Check if file exists in S3.
        
        Args:
            file_path: S3 key (path) of the file
        
        Returns:
            True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            return True
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == '404':
                return False
            # For other errors, log and return False
            logger.warning(f"Error checking file existence: {error_code}")
            return False
        
        except BotoCoreError:
            return False
